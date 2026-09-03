"""
SkillTrace AI - Performance Refactor Regression Test
Verify N+1 → batched query refactor maintains correct response shapes and behavior.
"""
import requests
import json
import time
from datetime import datetime

# Backend URL
BASE_URL = "https://c0f54cf7-a004-4df4-912a-b2565ec57ccc.preview.emergentagent.com/api"

# Test credentials
CREDENTIALS = {
    "super_admin": {"email": "admin@skilltrace.gov.in", "password": "Admin@123"},
    "provider": {"email": "provider@skilltrace.gov.in", "password": "Provider@123"},
    "district_admin": {"email": "district@skilltrace.gov.in", "password": "District@123"},
    "state_admin": {"email": "state@skilltrace.gov.in", "password": "State@123"},
}

tokens = {}
test_data = {}

def log_test(area, test_name, passed, details=""):
    """Log test results"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status} [{area}] {test_name}")
    if details:
        print(f"   {details}")
    return passed

def login(role):
    """Login and return token"""
    if role in tokens:
        return tokens[role]
    
    creds = CREDENTIALS[role]
    resp = requests.post(f"{BASE_URL}/auth/login", json=creds)
    if resp.status_code == 200:
        data = resp.json()
        tokens[role] = data["access_token"]
        # Get user info
        me_resp = requests.get(f"{BASE_URL}/auth/me", 
                              headers={"Authorization": f"Bearer {tokens[role]}"})
        if me_resp.status_code == 200:
            test_data[f"{role}_user"] = me_resp.json()
        return tokens[role]
    else:
        print(f"❌ Login failed for {role}: {resp.status_code} - {resp.text}")
        return None

def get_headers(role):
    """Get authorization headers for a role"""
    token = login(role)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}

# ===========================================================================
# TEST 1: GET /api/analytics/provider/{provider_id}/summary
# ===========================================================================
def test_provider_summary():
    """Test provider summary endpoint shape and correctness"""
    print("\n" + "="*70)
    print("TEST 1: GET /api/analytics/provider/{provider_id}/summary")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # Get provider_id from /api/auth/me
    provider_user = test_data.get("provider_user")
    if not provider_user or not provider_user.get("provider_id"):
        print("❌ Provider user has no provider_id")
        return False
    
    provider_id = provider_user["provider_id"]
    print(f"Testing with provider_id: {provider_id}")
    
    # Call the endpoint
    resp = requests.get(f"{BASE_URL}/analytics/provider/{provider_id}/summary", headers=headers)
    
    if resp.status_code != 200:
        results.append(log_test("PROVIDER_SUMMARY", "Endpoint returns 200", False,
                               f"Status: {resp.status_code}, Error: {resp.text[:200]}"))
        return False
    
    data = resp.json()
    
    # Verify response shape
    has_provider = "provider" in data
    results.append(log_test("PROVIDER_SUMMARY", "Response has 'provider' field", has_provider))
    
    has_summary = "summary" in data
    results.append(log_test("PROVIDER_SUMMARY", "Response has 'summary' field", has_summary))
    
    has_courses = "courses" in data
    results.append(log_test("PROVIDER_SUMMARY", "Response has 'courses' field", has_courses))
    
    # Verify summary shape
    if has_summary:
        summary = data["summary"]
        required_summary_fields = [
            "total_trainees", "certified", "placement_rate", 
            "employment_breakdown", "wage_distribution", 
            "verified_count", "confidence_breakdown", "reachable_rate"
        ]
        for field in required_summary_fields:
            has_field = field in summary
            results.append(log_test("PROVIDER_SUMMARY", f"summary.{field} exists", has_field))
        
        # Sanity checks
        total_trainees = summary.get("total_trainees", 0)
        placement_rate = summary.get("placement_rate", 0)
        
        trainees_positive = total_trainees > 0
        results.append(log_test("PROVIDER_SUMMARY", "summary.total_trainees > 0", trainees_positive,
                               f"total_trainees: {total_trainees}"))
        
        rate_valid = 0 <= placement_rate <= 100
        results.append(log_test("PROVIDER_SUMMARY", "placement_rate between 0-100", rate_valid,
                               f"placement_rate: {placement_rate}"))
    
    # Verify courses shape
    if has_courses:
        courses = data["courses"]
        courses_non_empty = len(courses) > 0
        results.append(log_test("PROVIDER_SUMMARY", "courses[] non-empty", courses_non_empty,
                               f"courses count: {len(courses)}"))
        
        if courses_non_empty:
            course = courses[0]
            required_course_fields = [
                "program_id", "course_name", "sector", 
                "placement_rate", "total_trainees"
            ]
            for field in required_course_fields:
                has_field = field in course
                results.append(log_test("PROVIDER_SUMMARY", f"courses[0].{field} exists", has_field))
            
            course_trainees = course.get("total_trainees", 0)
            course_trainees_positive = course_trainees > 0
            results.append(log_test("PROVIDER_SUMMARY", "courses[0].total_trainees > 0", course_trainees_positive,
                                   f"total_trainees: {course_trainees}"))
    
    return all(results)

# ===========================================================================
# TEST 2: GET /api/trainees-overview
# ===========================================================================
def test_trainees_overview():
    """Test trainees-overview endpoint shape and access control"""
    print("\n" + "="*70)
    print("TEST 2: GET /api/trainees-overview")
    print("="*70)
    
    results = []
    
    # Test 2a: As provider (should work)
    headers = get_headers("provider")
    if not headers:
        return False
    
    provider_user = test_data.get("provider_user")
    provider_id = provider_user.get("provider_id") if provider_user else None
    
    resp = requests.get(f"{BASE_URL}/trainees-overview", headers=headers)
    
    if resp.status_code != 200:
        results.append(log_test("TRAINEES_OVERVIEW", "Provider can access without provider_id param", False,
                               f"Status: {resp.status_code}"))
        return False
    
    data = resp.json()
    
    # Verify response shape
    has_items = "items" in data
    results.append(log_test("TRAINEES_OVERVIEW", "Response has 'items' field", has_items))
    
    has_total = "total" in data
    results.append(log_test("TRAINEES_OVERVIEW", "Response has 'total' field", has_total))
    
    if has_total and has_items:
        total = data["total"]
        items = data["items"]
        total_matches = total == len(items)
        results.append(log_test("TRAINEES_OVERVIEW", "total matches len(items)", total_matches,
                               f"total: {total}, len(items): {len(items)}"))
    
    # Verify items shape
    if has_items and len(data["items"]) > 0:
        item = data["items"][0]
        required_fields = [
            "trainee_id", "full_name", "district", "gender", "consent_given",
            "course_name", "sector", "attendance_percent", "assessment_score",
            "certified", "latest_followup_status", "latest_followup_interval",
            "confidence_score"
        ]
        for field in required_fields:
            has_field = field in item
            results.append(log_test("TRAINEES_OVERVIEW", f"items[0].{field} exists", has_field))
    
    # Test 2b: As super_admin WITHOUT provider_id → should return 403
    admin_headers = get_headers("super_admin")
    if admin_headers:
        resp = requests.get(f"{BASE_URL}/trainees-overview", headers=admin_headers)
        admin_403 = resp.status_code == 403
        results.append(log_test("TRAINEES_OVERVIEW", "super_admin WITHOUT provider_id returns 403", admin_403,
                               f"Status: {resp.status_code}"))
        
        # Test 2c: As super_admin WITH provider_id → should work
        if provider_id:
            resp = requests.get(f"{BASE_URL}/trainees-overview?provider_id={provider_id}",
                              headers=admin_headers)
            admin_with_provider_ok = resp.status_code == 200
            results.append(log_test("TRAINEES_OVERVIEW", "super_admin WITH provider_id returns 200", admin_with_provider_ok,
                                   f"Status: {resp.status_code}"))
    
    # Test 2d: As state_admin WITHOUT provider_id → should return 403
    state_headers = get_headers("state_admin")
    if state_headers:
        resp = requests.get(f"{BASE_URL}/trainees-overview", headers=state_headers)
        state_403 = resp.status_code == 403
        results.append(log_test("TRAINEES_OVERVIEW", "state_admin WITHOUT provider_id returns 403", state_403,
                               f"Status: {resp.status_code}"))
    
    return all(results)

# ===========================================================================
# TEST 3: GET /api/analytics/provider/{provider_id}/at-risk-trainees
# ===========================================================================
def test_at_risk_trainees():
    """Test at-risk-trainees endpoint with level filtering"""
    print("\n" + "="*70)
    print("TEST 3: GET /api/analytics/provider/{provider_id}/at-risk-trainees")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    provider_user = test_data.get("provider_user")
    if not provider_user or not provider_user.get("provider_id"):
        print("❌ Provider user has no provider_id")
        return False
    
    provider_id = provider_user["provider_id"]
    
    # Test 3a: level=high (only high-risk trainees)
    resp = requests.get(f"{BASE_URL}/analytics/provider/{provider_id}/at-risk-trainees?level=high",
                       headers=headers)
    
    if resp.status_code != 200:
        results.append(log_test("AT_RISK", "level=high returns 200", False,
                               f"Status: {resp.status_code}"))
        return False
    
    data = resp.json()
    
    # Verify response shape
    has_at_risk = "at_risk_trainees" in data
    results.append(log_test("AT_RISK", "Response has 'at_risk_trainees' field", has_at_risk))
    
    # Verify items shape
    if has_at_risk and len(data["at_risk_trainees"]) > 0:
        item = data["at_risk_trainees"][0]
        required_fields = [
            "trainee_id", "full_name", "district", "risk_score",
            "risk_level", "top_contributing_factors", "course_sector"
        ]
        for field in required_fields:
            has_field = field in item
            results.append(log_test("AT_RISK", f"at_risk_trainees[0].{field} exists", has_field))
        
        # Verify all returned rows have risk_level == 'high' for level=high
        all_high = all(t.get("risk_level") == "high" for t in data["at_risk_trainees"])
        results.append(log_test("AT_RISK", "level=high: all rows have risk_level='high'", all_high,
                               f"Count: {len(data['at_risk_trainees'])}"))
    else:
        print("   ℹ️  No high-risk trainees found (this is OK if data has none)")
    
    # Test 3b: level=medium (high + medium)
    resp = requests.get(f"{BASE_URL}/analytics/provider/{provider_id}/at-risk-trainees?level=medium",
                       headers=headers)
    
    if resp.status_code == 200:
        data_medium = resp.json()
        if len(data_medium.get("at_risk_trainees", [])) > 0:
            allowed_levels = {"high", "medium"}
            all_valid = all(t.get("risk_level") in allowed_levels 
                          for t in data_medium["at_risk_trainees"])
            results.append(log_test("AT_RISK", "level=medium: rows have risk_level in {high, medium}", all_valid,
                                   f"Count: {len(data_medium['at_risk_trainees'])}"))
        else:
            print("   ℹ️  No medium/high-risk trainees found")
    
    # Test 3c: level=all (high + medium + low)
    resp = requests.get(f"{BASE_URL}/analytics/provider/{provider_id}/at-risk-trainees?level=all",
                       headers=headers)
    
    if resp.status_code == 200:
        data_all = resp.json()
        results.append(log_test("AT_RISK", "level=all returns 200", True,
                               f"Count: {len(data_all.get('at_risk_trainees', []))}"))
    
    return all(results)

# ===========================================================================
# TEST 4: GET /api/analytics/overview (with drill-down)
# ===========================================================================
def test_analytics_overview():
    """Test analytics overview with and without provider_id drill-down"""
    print("\n" + "="*70)
    print("TEST 4: GET /api/analytics/overview")
    print("="*70)
    
    results = []
    headers = get_headers("super_admin")
    if not headers:
        return False
    
    # Test 4a: Without filter (all data)
    resp = requests.get(f"{BASE_URL}/analytics/overview", headers=headers)
    
    if resp.status_code != 200:
        results.append(log_test("OVERVIEW", "Endpoint returns 200", False,
                               f"Status: {resp.status_code}"))
        return False
    
    data_all = resp.json()
    
    # Verify response shape
    required_fields = [
        "totals", "by_provider", "by_sector", 
        "non_placement_reasons", "confidence_breakdown", "district_ranking"
    ]
    for field in required_fields:
        has_field = field in data_all
        results.append(log_test("OVERVIEW", f"Response has '{field}' field", has_field))
    
    # Verify by_provider shape
    if "by_provider" in data_all and len(data_all["by_provider"]) > 0:
        provider_row = data_all["by_provider"][0]
        for field in ["name", "placement_rate", "total"]:
            has_field = field in provider_row
            results.append(log_test("OVERVIEW", f"by_provider[0].{field} exists", has_field))
    
    # Verify by_sector shape
    if "by_sector" in data_all and len(data_all["by_sector"]) > 0:
        sector_row = data_all["by_sector"][0]
        for field in ["sector", "placement_rate", "total"]:
            has_field = field in sector_row
            results.append(log_test("OVERVIEW", f"by_sector[0].{field} exists", has_field))
    
    # Verify district_ranking shape
    if "district_ranking" in data_all and len(data_all["district_ranking"]) > 0:
        district_row = data_all["district_ranking"][0]
        for field in ["district", "placement_rate", "total"]:
            has_field = field in district_row
            results.append(log_test("OVERVIEW", f"district_ranking[0].{field} exists", has_field))
    
    # Test 4b: With provider_id drill-down
    provider_user = test_data.get("provider_user")
    if provider_user and provider_user.get("provider_id"):
        provider_id = provider_user["provider_id"]
        resp = requests.get(f"{BASE_URL}/analytics/overview?provider_id={provider_id}",
                          headers=headers)
        
        if resp.status_code == 200:
            data_filtered = resp.json()
            
            # Verify drill-down reduces total_trainees
            total_all = data_all.get("totals", {}).get("total_trainees", 0)
            total_filtered = data_filtered.get("totals", {}).get("total_trainees", 0)
            
            drill_down_works = total_filtered < total_all
            results.append(log_test("OVERVIEW", "provider_id drill-down reduces total_trainees", drill_down_works,
                                   f"All: {total_all}, Filtered: {total_filtered}"))
        else:
            results.append(log_test("OVERVIEW", "provider_id drill-down returns 200", False,
                                   f"Status: {resp.status_code}"))
    
    return all(results)

# ===========================================================================
# TEST 5: Full Phase 6 Privacy Regression
# ===========================================================================
def test_phase6_regression():
    """Quick regression of Phase 6 privacy features"""
    print("\n" + "="*70)
    print("TEST 5: Phase 6 Privacy Regression")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # Test 5a: Create trainee with consent scope EXCLUDING wage_data
    trainee_no_wage = {
        "full_name": f"Regression Test {int(time.time())}",
        "phone_number": f"9999{int(time.time()) % 1000000:06d}",
        "dob": "1999-06-10",
        "gender": "Female",
        "district": "Nagpur",
        "state": "Maharashtra",
        "consent": {
            "given": True,
            "scope": ["employment_status", "contact_for_verification"]  # NO wage_data
        }
    }
    resp = requests.post(f"{BASE_URL}/trainees", json=trainee_no_wage, headers=headers)
    if resp.status_code == 200 and resp.json().get("created"):
        trainee_id = resp.json()["_id"]
        results.append(log_test("PRIVACY", "Create trainee without wage consent", True))
        
        # Test 5b: POST /api/employment with wage_bracket → wage should be dropped
        employment_data = {
            "trainee_id": trainee_id,
            "type": "employed",
            "employer_name": "Test Corp",
            "sector": "Manufacturing",
            "wage_bracket": "15-25k"
        }
        resp = requests.post(f"{BASE_URL}/employment", json=employment_data, headers=headers)
        wage_dropped = resp.status_code == 200 and resp.json().get("wage_bracket") is None
        results.append(log_test("PRIVACY", "Wage dropped when consent excludes wage_data", wage_dropped))
        
        # Test 5c: wage-progression returns wage_consent:false
        resp = requests.get(f"{BASE_URL}/trainees/{trainee_id}/wage-progression", headers=headers)
        wage_consent_false = (resp.status_code == 200 and 
                             resp.json().get("wage_consent") == False)
        results.append(log_test("PRIVACY", "wage-progression returns wage_consent:false", wage_consent_false))
    else:
        results.append(log_test("PRIVACY", "Create trainee without wage consent", False))
    
    # Test 5d: Admin endpoints return 403 without provider_id
    admin_headers = get_headers("super_admin")
    if admin_headers:
        resp = requests.get(f"{BASE_URL}/trainees-overview", headers=admin_headers)
        admin_403 = resp.status_code == 403
        results.append(log_test("PRIVACY", "Admin trainees-overview 403 without provider_id", admin_403))
    
    # Test 5e: ML endpoints still work
    resp = requests.get(f"{BASE_URL}/ml/health")
    ml_ok = resp.status_code == 200
    results.append(log_test("PRIVACY", "ML health endpoint works", ml_ok))
    
    return all(results)

# ===========================================================================
# TEST 6: Auth for all 4 roles + brute-force lockout
# ===========================================================================
def test_auth_regression():
    """Quick auth regression"""
    print("\n" + "="*70)
    print("TEST 6: Auth Regression")
    print("="*70)
    
    results = []
    
    # Test all 4 roles can login
    for role in ["super_admin", "provider", "district_admin", "state_admin"]:
        resp = requests.post(f"{BASE_URL}/auth/login", json=CREDENTIALS[role])
        passed = resp.status_code == 200 and "access_token" in resp.json()
        results.append(log_test("AUTH", f"Login {role}", passed))
    
    # Test brute-force lockout
    throwaway_email = f"lockout_{int(time.time())}@test.com"
    lockout_triggered = False
    for i in range(6):
        resp = requests.post(f"{BASE_URL}/auth/login",
                           json={"email": throwaway_email, "password": "wrong"})
        if resp.status_code == 429:
            lockout_triggered = True
            break
    results.append(log_test("AUTH", "Brute-force lockout returns 429", lockout_triggered))
    
    return all(results)

# ===========================================================================
# MAIN TEST RUNNER
# ===========================================================================
def main():
    """Run all regression tests"""
    print("\n" + "="*70)
    print("SKILLTRACE AI - PERFORMANCE REFACTOR REGRESSION TEST")
    print("N+1 → Batched Query Refactor Verification")
    print("="*70)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test started: {datetime.now().isoformat()}")
    
    results = {
        "1_PROVIDER_SUMMARY": False,
        "2_TRAINEES_OVERVIEW": False,
        "3_AT_RISK_TRAINEES": False,
        "4_ANALYTICS_OVERVIEW": False,
        "5_PHASE6_REGRESSION": False,
        "6_AUTH_REGRESSION": False,
    }
    
    try:
        results["1_PROVIDER_SUMMARY"] = test_provider_summary()
    except Exception as e:
        print(f"\n❌ EXCEPTION in PROVIDER_SUMMARY: {str(e)}")
    
    try:
        results["2_TRAINEES_OVERVIEW"] = test_trainees_overview()
    except Exception as e:
        print(f"\n❌ EXCEPTION in TRAINEES_OVERVIEW: {str(e)}")
    
    try:
        results["3_AT_RISK_TRAINEES"] = test_at_risk_trainees()
    except Exception as e:
        print(f"\n❌ EXCEPTION in AT_RISK_TRAINEES: {str(e)}")
    
    try:
        results["4_ANALYTICS_OVERVIEW"] = test_analytics_overview()
    except Exception as e:
        print(f"\n❌ EXCEPTION in ANALYTICS_OVERVIEW: {str(e)}")
    
    try:
        results["5_PHASE6_REGRESSION"] = test_phase6_regression()
    except Exception as e:
        print(f"\n❌ EXCEPTION in PHASE6_REGRESSION: {str(e)}")
    
    try:
        results["6_AUTH_REGRESSION"] = test_auth_regression()
    except Exception as e:
        print(f"\n❌ EXCEPTION in AUTH_REGRESSION: {str(e)}")
    
    # Final Summary
    print("\n" + "="*70)
    print("FINAL SUMMARY - REGRESSION TEST")
    print("="*70)
    
    for area, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {area.replace('_', ' ')}")
    
    total_passed = sum(1 for v in results.values() if v)
    total_tests = len(results)
    
    print("\n" + "="*70)
    print(f"OVERALL: {total_passed}/{total_tests} test areas passed")
    print("="*70)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

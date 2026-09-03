"""
SkillTrace AI Backend Health Check
Full verification of all backend areas (A-G) as per SIH 2026 review request.
"""
import requests
import json
import time
from datetime import datetime, timedelta

# Backend URL from frontend/.env
BASE_URL = "https://c0f54cf7-a004-4df4-912a-b2565ec57ccc.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
CREDENTIALS = {
    "super_admin": {"email": "admin@skilltrace.gov.in", "password": "Admin@123"},
    "provider": {"email": "provider@skilltrace.gov.in", "password": "Provider@123"},
    "district_admin": {"email": "district@skilltrace.gov.in", "password": "District@123"},
    "state_admin": {"email": "state@skilltrace.gov.in", "password": "State@123"},
}

# Store tokens and test data
tokens = {}
test_data = {}

def log_test(area, test_name, passed, details=""):
    """Log test results"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status} [{area}] {test_name}")
    if details:
        print(f"   Details: {details}")
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
# (A) AUTH + RBAC
# ===========================================================================
def test_auth_rbac():
    """Test authentication and role-based access control"""
    print("\n" + "="*70)
    print("(A) AUTH + RBAC TESTS")
    print("="*70)
    
    results = []
    
    # Test 1: Login works for all 4 roles returning JWT
    for role in ["super_admin", "provider", "district_admin", "state_admin"]:
        resp = requests.post(f"{BASE_URL}/auth/login", json=CREDENTIALS[role])
        passed = resp.status_code == 200 and "access_token" in resp.json()
        if passed:
            tokens[role] = resp.json()["access_token"]
        results.append(log_test("AUTH", f"Login {role}", passed, 
                               f"Status: {resp.status_code}"))
    
    # Test 2: Invalid password returns 401
    resp = requests.post(f"{BASE_URL}/auth/login", 
                        json={"email": "admin@skilltrace.gov.in", "password": "WrongPassword123"})
    results.append(log_test("AUTH", "Invalid password returns 401", 
                           resp.status_code == 401,
                           f"Status: {resp.status_code}"))
    
    # Test 3: Brute-force lockout returns 429 (use throwaway email)
    throwaway_email = f"lockout_test_{int(time.time())}@test.com"
    lockout_triggered = False
    for i in range(6):
        resp = requests.post(f"{BASE_URL}/auth/login",
                           json={"email": throwaway_email, "password": "wrong"})
        if resp.status_code == 429:
            lockout_triggered = True
            break
    results.append(log_test("AUTH", "Brute-force lockout returns 429", 
                           lockout_triggered,
                           f"Final status: {resp.status_code}"))
    
    return all(results)

# ===========================================================================
# (B) TRAINEES + CONSENT
# ===========================================================================
def test_trainees_consent():
    """Test trainee creation, consent management, and duplicate detection"""
    print("\n" + "="*70)
    print("(B) TRAINEES + CONSENT TESTS")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # Test 1: POST /api/trainees creates a trainee capturing consent
    trainee_data = {
        "full_name": f"Test Trainee {int(time.time())}",
        "phone_number": f"9876{int(time.time()) % 1000000:06d}",
        "dob": "2000-05-15",
        "gender": "Female",
        "district": "Mumbai",
        "state": "Maharashtra",
        "consent": {
            "given": True,
            "scope": ["employment_status", "wage_data", "contact_for_verification"]
        }
    }
    resp = requests.post(f"{BASE_URL}/trainees", json=trainee_data, headers=headers)
    passed = resp.status_code == 200 and resp.json().get("created") == True
    if passed:
        test_data["trainee_id"] = resp.json()["_id"]
    results.append(log_test("TRAINEES", "Create trainee with consent", passed,
                           f"Status: {resp.status_code}, ID: {test_data.get('trainee_id', 'N/A')}"))
    
    # Test 2: GET /api/trainees/{id}
    if "trainee_id" in test_data:
        resp = requests.get(f"{BASE_URL}/trainees/{test_data['trainee_id']}", headers=headers)
        passed = resp.status_code == 200 and "trainee" in resp.json()
        results.append(log_test("TRAINEES", "Get trainee by ID", passed,
                               f"Status: {resp.status_code}"))
    
    # Test 3: PATCH /api/trainees/{id}/consent updates scope
    if "trainee_id" in test_data:
        new_consent = {
            "given": True,
            "scope": ["employment_status", "contact_for_verification"]  # Removed wage_data
        }
        resp = requests.patch(f"{BASE_URL}/trainees/{test_data['trainee_id']}/consent",
                             json=new_consent, headers=headers)
        passed = resp.status_code == 200 and resp.json().get("action") in ["scope_updated", "granted"]
        results.append(log_test("TRAINEES", "Update consent scope", passed,
                               f"Status: {resp.status_code}, Action: {resp.json().get('action', 'N/A')}"))
    
    # Test 4: Duplicate identity-match triggers on near-duplicate create
    duplicate_data = trainee_data.copy()
    duplicate_data["full_name"] = trainee_data["full_name"]  # Same name
    resp = requests.post(f"{BASE_URL}/trainees", json=duplicate_data, headers=headers)
    is_duplicate_check = resp.status_code == 200 and resp.json().get("is_likely_duplicate") == True
    results.append(log_test("TRAINEES", "Duplicate detection triggers", is_duplicate_check,
                           f"Status: {resp.status_code}, Duplicate: {resp.json().get('is_likely_duplicate', False)}"))
    
    # Test 5: Use ?force=true to bypass duplicate check
    resp = requests.post(f"{BASE_URL}/trainees?force=true", json=duplicate_data, headers=headers)
    passed = resp.status_code == 200 and resp.json().get("created") == True
    if passed:
        test_data["duplicate_trainee_id"] = resp.json()["_id"]
    results.append(log_test("TRAINEES", "Bypass duplicate with ?force=true", passed,
                           f"Status: {resp.status_code}"))
    
    return all(results)

# ===========================================================================
# (C) ENROLLMENTS + FOLLOWUPS
# ===========================================================================
def test_enrollments_followups():
    """Test enrollment creation and follow-up scheduling/responding"""
    print("\n" + "="*70)
    print("(C) ENROLLMENTS + FOLLOWUPS TESTS")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # First, get a program_id
    resp = requests.get(f"{BASE_URL}/programs", headers=headers)
    if resp.status_code == 200 and len(resp.json()) > 0:
        test_data["program_id"] = resp.json()[0]["_id"]
    else:
        print("⚠️  No programs found, skipping enrollment tests")
        return False
    
    # Test 1: POST /api/enrollments
    if "trainee_id" in test_data:
        cert_date = (datetime.now() - timedelta(days=60)).date().isoformat()
        enrollment_data = {
            "trainee_id": test_data["trainee_id"],
            "program_id": test_data["program_id"],
            "attendance_percent": 85.5,
            "assessment_score": 78.0,
            "certified": True,
            "certification_date": cert_date
        }
        resp = requests.post(f"{BASE_URL}/enrollments", json=enrollment_data, headers=headers)
        passed = resp.status_code == 200 and "_id" in resp.json()
        if passed:
            test_data["enrollment_id"] = resp.json()["_id"]
        results.append(log_test("ENROLLMENTS", "Create enrollment", passed,
                               f"Status: {resp.status_code}, ID: {test_data.get('enrollment_id', 'N/A')}"))
    
    # Test 2: POST /api/followups/schedule creates followups from certification
    if "enrollment_id" in test_data:
        resp = requests.post(f"{BASE_URL}/followups/schedule",
                           json={"enrollment_id": test_data["enrollment_id"]},
                           headers=headers)
        passed = resp.status_code == 200 and resp.json().get("followups_created", 0) > 0
        results.append(log_test("FOLLOWUPS", "Schedule followups", passed,
                               f"Status: {resp.status_code}, Created: {resp.json().get('followups_created', 0)}"))
    
    # Test 3: Get a followup to respond to
    if "trainee_id" in test_data:
        resp = requests.get(f"{BASE_URL}/followups?trainee_id={test_data['trainee_id']}&status=pending",
                          headers=headers)
        if resp.status_code == 200 and len(resp.json().get("items", [])) > 0:
            test_data["followup_id"] = resp.json()["items"][0]["_id"]
    
    # Test 4: POST /api/followups/{id}/respond with structured_response
    if "followup_id" in test_data:
        structured_data = {
            "channel_used": "whatsapp",
            "structured_response": {
                "employment_type": "employed",
                "wage_bracket": "15-25k"
            }
        }
        resp = requests.post(f"{BASE_URL}/followups/{test_data['followup_id']}/respond",
                           json=structured_data, headers=headers)
        passed = resp.status_code == 200 and resp.json().get("status") == "responded"
        results.append(log_test("FOLLOWUPS", "Respond with structured data", passed,
                               f"Status: {resp.status_code}"))
    
    # Test 5: Create another followup and respond with raw_response_text (ML classification)
    # Schedule more followups to get another pending one
    if "enrollment_id" in test_data:
        resp = requests.get(f"{BASE_URL}/followups?trainee_id={test_data['trainee_id']}&status=pending",
                          headers=headers)
        if resp.status_code == 200 and len(resp.json().get("items", [])) > 0:
            followup_id_2 = resp.json()["items"][0]["_id"]
            raw_text_data = {
                "channel_used": "whatsapp",
                "raw_response_text": "I got a job at a local factory earning around 18000 rupees per month"
            }
            resp = requests.post(f"{BASE_URL}/followups/{followup_id_2}/respond",
                               json=raw_text_data, headers=headers)
            passed = (resp.status_code == 200 and 
                     resp.json().get("status") == "responded" and
                     resp.json().get("structured_response") is not None)
            results.append(log_test("FOLLOWUPS", "Respond with raw text (ML classify)", passed,
                                   f"Status: {resp.status_code}, ML classified: {resp.json().get('structured_response') is not None}"))
    
    return all(results)

# ===========================================================================
# (D) EMPLOYMENT + PUBLIC VERIFY
# ===========================================================================
def test_employment_verify():
    """Test employment record creation and public verification flow"""
    print("\n" + "="*70)
    print("(D) EMPLOYMENT + PUBLIC VERIFY TESTS")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # Test 1: POST /api/employment
    if "trainee_id" in test_data:
        employment_data = {
            "trainee_id": test_data["trainee_id"],
            "type": "employed",
            "employer_name": "Tech Solutions Pvt Ltd",
            "employer_contact": "hr@techsolutions.com",
            "sector": "IT",
            "wage_bracket": "15-25k"
        }
        resp = requests.post(f"{BASE_URL}/employment", json=employment_data, headers=headers)
        passed = resp.status_code == 200 and "_id" in resp.json()
        if passed:
            test_data["employment_id"] = resp.json()["_id"]
        results.append(log_test("EMPLOYMENT", "Create employment record", passed,
                               f"Status: {resp.status_code}, ID: {test_data.get('employment_id', 'N/A')}"))
    
    # Test 2: Request verification token
    if "employment_id" in test_data:
        resp = requests.post(f"{BASE_URL}/employment/{test_data['employment_id']}/request-verification",
                           headers=headers)
        passed = resp.status_code == 200 and "token" in resp.json()
        if passed:
            test_data["verification_token"] = resp.json()["token"]
        results.append(log_test("EMPLOYMENT", "Request verification token", passed,
                               f"Status: {resp.status_code}, Token: {test_data.get('verification_token', 'N/A')[:20]}..."))
    
    # Test 3: POST /api/employment/verify/{token} (public, no auth)
    if "verification_token" in test_data:
        verify_data = {
            "confirmed": True,
            "employer_name": "Tech Solutions Pvt Ltd"
        }
        resp = requests.post(f"{BASE_URL}/employment/verify/{test_data['verification_token']}",
                           json=verify_data)  # No headers - public endpoint
        passed = resp.status_code == 200 and resp.json().get("employer_verified") == True
        results.append(log_test("EMPLOYMENT", "Public verify endpoint (no auth)", passed,
                               f"Status: {resp.status_code}, Verified: {resp.json().get('employer_verified', False)}"))
    
    return all(results)

# ===========================================================================
# (E) PHASE 6 PRIVACY (MOST IMPORTANT)
# ===========================================================================
def test_phase6_privacy():
    """Test Phase 6 privacy features - consent scope enforcement, revocation, audit logs"""
    print("\n" + "="*70)
    print("(E) PHASE 6 PRIVACY TESTS (MOST IMPORTANT)")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # Test 1: Create trainee with consent scope that EXCLUDES "wage_data"
    trainee_no_wage = {
        "full_name": f"No Wage Consent {int(time.time())}",
        "phone_number": f"9123{int(time.time()) % 1000000:06d}",
        "dob": "1998-03-20",
        "gender": "Male",
        "district": "Pune",
        "state": "Maharashtra",
        "consent": {
            "given": True,
            "scope": ["employment_status", "contact_for_verification"]  # NO wage_data
        }
    }
    resp = requests.post(f"{BASE_URL}/trainees", json=trainee_no_wage, headers=headers)
    if resp.status_code == 200 and resp.json().get("created"):
        test_data["no_wage_trainee_id"] = resp.json()["_id"]
        results.append(log_test("PRIVACY", "Create trainee without wage consent", True,
                               f"ID: {test_data['no_wage_trainee_id']}"))
        
        # Test 1b: POST /api/employment with wage_bracket -> wage should be DROPPED/None
        employment_with_wage = {
            "trainee_id": test_data["no_wage_trainee_id"],
            "type": "employed",
            "employer_name": "Test Company",
            "sector": "Manufacturing",
            "wage_bracket": "15-25k"  # Trying to set wage
        }
        resp = requests.post(f"{BASE_URL}/employment", json=employment_with_wage, headers=headers)
        wage_dropped = resp.status_code == 200 and resp.json().get("wage_bracket") is None
        results.append(log_test("PRIVACY", "Wage dropped when consent excludes wage_data", wage_dropped,
                               f"Status: {resp.status_code}, Wage: {resp.json().get('wage_bracket', 'None')}"))
        
        # Test 1c: GET /api/trainees/{id}/wage-progression returns wage_consent:false
        resp = requests.get(f"{BASE_URL}/trainees/{test_data['no_wage_trainee_id']}/wage-progression",
                          headers=headers)
        wage_consent_false = (resp.status_code == 200 and 
                             resp.json().get("wage_consent") == False and
                             len(resp.json().get("points", [])) == 0)
        results.append(log_test("PRIVACY", "Wage progression returns wage_consent:false", wage_consent_false,
                               f"Status: {resp.status_code}, wage_consent: {resp.json().get('wage_consent')}"))
    else:
        results.append(log_test("PRIVACY", "Create trainee without wage consent", False,
                               f"Failed to create trainee: {resp.status_code}"))
    
    # Test 2: Revoke consent and verify PII anonymization
    if "trainee_id" in test_data:
        # Get provider's total_trainees count before revocation
        resp = requests.get(f"{BASE_URL}/providers", headers=headers)
        providers = resp.json()
        provider_id = None
        initial_count = 0
        if len(providers) > 0:
            provider_id = providers[0]["_id"]
            # Get initial trainee count for this provider
            resp = requests.get(f"{BASE_URL}/trainees?provider_id={provider_id}", headers=headers)
            if resp.status_code == 200:
                initial_count = resp.json().get("total", 0)
        
        # Revoke consent
        resp = requests.post(f"{BASE_URL}/trainees/{test_data['trainee_id']}/revoke-consent",
                           headers=headers)
        revoke_success = resp.status_code == 200 and resp.json().get("anonymized") == True
        results.append(log_test("PRIVACY", "Revoke consent endpoint", revoke_success,
                               f"Status: {resp.status_code}, Anonymized: {resp.json().get('anonymized', False)}"))
        
        # Verify PII is anonymized
        resp = requests.get(f"{BASE_URL}/trainees/{test_data['trainee_id']}", headers=headers)
        if resp.status_code == 200:
            trainee = resp.json()["trainee"]
            pii_anonymized = (trainee["full_name"].startswith("Anonymized Trainee") and
                            trainee["phone_masked"] == "REDACTED" and
                            trainee.get("consent", {}).get("given") == False)
            results.append(log_test("PRIVACY", "PII anonymized after revocation", pii_anonymized,
                                   f"Name: {trainee['full_name']}, Phone: {trainee['phone_masked']}"))
        
        # Test 2b: Write paths return 403 for revoked trainee
        employment_data = {
            "trainee_id": test_data["trainee_id"],
            "type": "employed",
            "employer_name": "Should Fail",
            "sector": "IT"
        }
        resp = requests.post(f"{BASE_URL}/employment", json=employment_data, headers=headers)
        write_blocked = resp.status_code == 403
        results.append(log_test("PRIVACY", "Write paths blocked for revoked trainee", write_blocked,
                               f"Status: {resp.status_code}"))
    
    # Test 3: GET /api/trainees/{id}/consent-logs shows audit entries
    if "trainee_id" in test_data:
        resp = requests.get(f"{BASE_URL}/trainees/{test_data['trainee_id']}/consent-logs",
                          headers=headers)
        if resp.status_code == 200:
            logs = resp.json().get("items", [])
            has_granted = any(log["action"] == "granted" for log in logs)
            has_accessed = any(log["action"] == "accessed" for log in logs)
            has_revoked = any(log["action"] == "revoked" for log in logs)
            audit_complete = has_granted and has_accessed and has_revoked
            results.append(log_test("PRIVACY", "Consent logs show audit trail", audit_complete,
                                   f"Logs: granted={has_granted}, accessed={has_accessed}, revoked={has_revoked}"))
        else:
            results.append(log_test("PRIVACY", "Consent logs show audit trail", False,
                                   f"Status: {resp.status_code}"))
    
    # Test 4: Admin endpoints return 403 without provider drill-down
    admin_headers = get_headers("super_admin")
    if admin_headers:
        # GET /api/trainees without provider_id should return 403
        resp = requests.get(f"{BASE_URL}/trainees", headers=admin_headers)
        trainees_403 = resp.status_code == 403
        results.append(log_test("PRIVACY", "GET /api/trainees returns 403 for admin without provider", trainees_403,
                               f"Status: {resp.status_code}"))
        
        # GET /api/trainees-overview without provider_id should return 403
        resp = requests.get(f"{BASE_URL}/trainees-overview", headers=admin_headers)
        overview_403 = resp.status_code == 403
        results.append(log_test("PRIVACY", "GET /api/trainees-overview returns 403 for admin without provider", overview_403,
                               f"Status: {resp.status_code}"))
    
    # Test 5: CSV export shows "(consent off)" for wage when consent is off
    if "no_wage_trainee_id" in test_data:
        resp = requests.get(f"{BASE_URL}/analytics/export.csv", headers=headers)
        if resp.status_code == 200:
            csv_content = resp.text
            has_consent_off = "(consent off)" in csv_content
            results.append(log_test("PRIVACY", "CSV export shows '(consent off)' for wage", has_consent_off,
                                   f"Status: {resp.status_code}, Contains '(consent off)': {has_consent_off}"))
        else:
            results.append(log_test("PRIVACY", "CSV export shows '(consent off)' for wage", False,
                                   f"Status: {resp.status_code}"))
    
    # Test 6: PDF export exists
    resp = requests.get(f"{BASE_URL}/analytics/export.pdf", headers=headers)
    pdf_exists = resp.status_code == 200 and resp.headers.get("content-type") == "application/pdf"
    results.append(log_test("PRIVACY", "PDF export endpoint works", pdf_exists,
                           f"Status: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}"))
    
    return all(results)

# ===========================================================================
# (F) ML ENDPOINTS
# ===========================================================================
def test_ml_endpoints():
    """Test ML endpoints for health, risk prediction, identity matching, response classification"""
    print("\n" + "="*70)
    print("(F) ML ENDPOINTS TESTS")
    print("="*70)
    
    results = []
    headers = get_headers("provider")
    if not headers:
        return False
    
    # Test 1: GET /api/ml/health
    resp = requests.get(f"{BASE_URL}/ml/health")
    health_ok = resp.status_code == 200 and resp.json().get("status") in ["ok", "degraded"]
    results.append(log_test("ML", "/api/ml/health", health_ok,
                           f"Status: {resp.status_code}, ML Status: {resp.json().get('status')}"))
    
    # Test 2: POST /api/ml/predict-risk
    risk_data = {
        "attendance_percent": 85.0,
        "assessment_score": 75.0,
        "course_sector": "IT",
        "district": "Mumbai",
        "gender": "Male",
        "age": 24
    }
    resp = requests.post(f"{BASE_URL}/ml/predict-risk", json=risk_data)
    risk_ok = (resp.status_code == 200 and 
              "risk_score" in resp.json() and
              "risk_level" in resp.json())
    results.append(log_test("ML", "/api/ml/predict-risk", risk_ok,
                           f"Status: {resp.status_code}, Risk: {resp.json().get('risk_level', 'N/A')}"))
    
    # Test 3: POST /api/ml/match-identity
    identity_data = {
        "name": "Rahul Kumar",
        "phone_last4": "1234",
        "dob": "2000-01-15",
        "district": "Mumbai"
    }
    resp = requests.post(f"{BASE_URL}/ml/match-identity", json=identity_data, headers=headers)
    identity_ok = resp.status_code == 200 and "is_likely_duplicate" in resp.json()
    results.append(log_test("ML", "/api/ml/match-identity", identity_ok,
                           f"Status: {resp.status_code}"))
    
    # Test 4: POST /api/ml/classify-response
    classify_data = {
        "raw_text": "I am working at a factory earning 20000 rupees monthly"
    }
    resp = requests.post(f"{BASE_URL}/ml/classify-response", json=classify_data)
    classify_ok = (resp.status_code == 200 and
                  "predicted_category" in resp.json() and
                  "confidence" in resp.json())
    results.append(log_test("ML", "/api/ml/classify-response", classify_ok,
                           f"Status: {resp.status_code}, Category: {resp.json().get('predicted_category', 'N/A')}"))
    
    return all(results)

# ===========================================================================
# (G) ANALYTICS
# ===========================================================================
def test_analytics():
    """Test analytics endpoints"""
    print("\n" + "="*70)
    print("(G) ANALYTICS TESTS")
    print("="*70)
    
    results = []
    headers = get_headers("super_admin")
    if not headers:
        return False
    
    # Test 1: GET /api/analytics/overview returns aggregates
    resp = requests.get(f"{BASE_URL}/analytics/overview", headers=headers)
    overview_ok = (resp.status_code == 200 and
                  "totals" in resp.json() and
                  "by_provider" in resp.json())
    results.append(log_test("ANALYTICS", "/api/analytics/overview", overview_ok,
                           f"Status: {resp.status_code}"))
    
    # Test 2: GET /api/analytics/overview supports provider_id filter
    resp = requests.get(f"{BASE_URL}/providers", headers=headers)
    if resp.status_code == 200 and len(resp.json()) > 0:
        provider_id = resp.json()[0]["_id"]
        resp = requests.get(f"{BASE_URL}/analytics/overview?provider_id={provider_id}",
                          headers=headers)
        filter_ok = resp.status_code == 200 and "totals" in resp.json()
        results.append(log_test("ANALYTICS", "/api/analytics/overview with provider_id filter", filter_ok,
                               f"Status: {resp.status_code}"))
    
    # Test 3: GET /api/analytics/provider/{id}/at-risk-trainees
    resp = requests.get(f"{BASE_URL}/providers", headers=headers)
    if resp.status_code == 200 and len(resp.json()) > 0:
        provider_id = resp.json()[0]["_id"]
        resp = requests.get(f"{BASE_URL}/analytics/provider/{provider_id}/at-risk-trainees",
                          headers=headers)
        at_risk_ok = (resp.status_code == 200 and
                     "at_risk_trainees" in resp.json())
        results.append(log_test("ANALYTICS", "/api/analytics/provider/{id}/at-risk-trainees", at_risk_ok,
                               f"Status: {resp.status_code}, Count: {resp.json().get('count', 0)}"))
    
    return all(results)

# ===========================================================================
# MAIN TEST RUNNER
# ===========================================================================
def main():
    """Run all backend health checks"""
    print("\n" + "="*70)
    print("SKILLTRACE AI BACKEND HEALTH CHECK")
    print("SIH 2026 - Full Backend Verification (Areas A-G)")
    print("="*70)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test started: {datetime.now().isoformat()}")
    
    results = {
        "A_AUTH_RBAC": False,
        "B_TRAINEES_CONSENT": False,
        "C_ENROLLMENTS_FOLLOWUPS": False,
        "D_EMPLOYMENT_VERIFY": False,
        "E_PHASE6_PRIVACY": False,
        "F_ML_ENDPOINTS": False,
        "G_ANALYTICS": False,
    }
    
    try:
        results["A_AUTH_RBAC"] = test_auth_rbac()
    except Exception as e:
        print(f"\n❌ EXCEPTION in AUTH_RBAC: {str(e)}")
    
    try:
        results["B_TRAINEES_CONSENT"] = test_trainees_consent()
    except Exception as e:
        print(f"\n❌ EXCEPTION in TRAINEES_CONSENT: {str(e)}")
    
    try:
        results["C_ENROLLMENTS_FOLLOWUPS"] = test_enrollments_followups()
    except Exception as e:
        print(f"\n❌ EXCEPTION in ENROLLMENTS_FOLLOWUPS: {str(e)}")
    
    try:
        results["D_EMPLOYMENT_VERIFY"] = test_employment_verify()
    except Exception as e:
        print(f"\n❌ EXCEPTION in EMPLOYMENT_VERIFY: {str(e)}")
    
    try:
        results["E_PHASE6_PRIVACY"] = test_phase6_privacy()
    except Exception as e:
        print(f"\n❌ EXCEPTION in PHASE6_PRIVACY: {str(e)}")
    
    try:
        results["F_ML_ENDPOINTS"] = test_ml_endpoints()
    except Exception as e:
        print(f"\n❌ EXCEPTION in ML_ENDPOINTS: {str(e)}")
    
    try:
        results["G_ANALYTICS"] = test_analytics()
    except Exception as e:
        print(f"\n❌ EXCEPTION in ANALYTICS: {str(e)}")
    
    # Final Summary
    print("\n" + "="*70)
    print("FINAL SUMMARY - BACKEND HEALTH CHECK")
    print("="*70)
    
    for area, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {area.replace('_', ' ')}")
    
    total_passed = sum(1 for v in results.values() if v)
    total_tests = len(results)
    
    print("\n" + "="*70)
    print(f"OVERALL: {total_passed}/{total_tests} areas passed")
    print("="*70)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

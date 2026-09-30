from src.security import hash_password,verify_password
def test_password_hash_round_trip():
 d,s=hash_password('test-password'); assert verify_password('test-password',d,s); assert not verify_password('wrong-password',d,s)

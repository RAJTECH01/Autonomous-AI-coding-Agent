def test_register_and_login_flow(client):
    # 1. Register a new user
    reg_response = client.post("/api/v1/auth/register", json={
        "email": "developer@example.com",
        "password": "password123",
        "full_name": "Senior Developer"
    })
    assert reg_response.status_code == 201
    user_data = reg_response.json()
    assert user_data["email"] == "developer@example.com"

    # 2. Login with registered user credentials
    login_response = client.post("/api/v1/auth/login", json={
        "email": "developer@example.com",
        "password": "password123"
    })
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"


def test_login_invalid_password(client):
    # Register user first
    client.post("/api/v1/auth/register", json={
        "email": "user2@example.com",
        "password": "password123",
        "full_name": "User Two"
    })

    # Attempt login with wrong password
    response = client.post("/api/v1/auth/login", json={
        "email": "user2@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401

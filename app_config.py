import os

CLIENT_ID = "94a09b79-7009-4edd-98d5-884e2b996e34" # Application (client) ID of app registration

# CLIENT_SECRET = "-3EnWN0~CJ_HoQVJ6eh3nP0VR4C3be.F.4" # Placeholder - for use ONLY during testing.

CLIENT_SECRET = os.getenv("MSFT_AUTH_CLIENT_SECRET")
if not CLIENT_SECRET:
    raise ValueError("Need to define MSFT_AUTH_CLIENT_SECRET environment variable")

# AUTHORITY = "https://login.microsoftonline.com/c8c69aae-32ba-43d1-9f59-f98c95fb227b"  # For multi-tenant app
AUTHORITY = "https://login.microsoftonline.com/c8c69aae-32ba-43d1-9f59-f98c95fb227b"

REDIRECT_PATH = "/getAToken"

ENDPOINT = 'https://graph.microsoft.com/v1.0/users'  # This resource requires no admin consent

SCOPE = ["User.ReadBasic.All"]

SESSION_TYPE = "filesystem"  # Specifies the token cache should be stored in server-side session

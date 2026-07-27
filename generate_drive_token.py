import os
from dotenv import load_dotenv

# Run: pip install google-auth-oauthlib
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Missing library! Please run:")
    print("pip install google-auth-oauthlib")
    exit(1)

# Load existing environment variables
load_dotenv()

# We request permission to manage files created by the app (the same scope the app uses)
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_refresh_token() -> bool:
    client_id = os.getenv('GOOGLE_DRIVE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_DRIVE_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("Error: GOOGLE_DRIVE_CLIENT_ID or GOOGLE_DRIVE_CLIENT_SECRET not found in your .env file.")
        print("Please make sure they are set before running this script.")
        return False

    # Build the required config structure dynamically from your .env
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    try:
        print("Opening your browser to authorize with Google Drive...")
        # Start local server to get the auth code from the browser redirect
        # prompt='consent' forces Google to issue a new refresh token
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        
        # Pass timeout to prevent hanging indefinitely
        timeout_seconds = int(os.getenv("GOOGLE_OAUTH_TIMEOUT_SECONDS", "300"))
        try:
            creds = flow.run_local_server(port=0, prompt='consent', access_type='offline', timeout_seconds=timeout_seconds)
        except TypeError:
            # Fallback if InstalledAppFlow version doesn't accept timeout_seconds
            creds = flow.run_local_server(port=0, prompt='consent', access_type='offline')
        
        if not creds or not creds.refresh_token:
            print("\n[WARNING] Google did not return a refresh token!")
            print("Try going to your Google Account permissions, revoking access to this app, and running the script again.")
            return False

        print("\n" + "="*50)
        print("SUCCESS! Your NEW Refresh Token has been generated.")
        print("="*50 + "\n")
        print(f"GOOGLE_DRIVE_REFRESH_TOKEN={creds.refresh_token}\n")
        print("="*50)
        print("NEXT STEPS:")
        print("1. Copy the token string above.")
        print("2. Paste it into your Vercel/PythonAnywhere server environment variables (or .env file) to replace the old expired one.")
        print("3. Restart/redeploy your web app.")
        return True
        
    except Exception as e:
        print(f"\nAn error occurred during authentication: {e}")
        return False

if __name__ == '__main__':
    raise SystemExit(0 if get_refresh_token() else 1)

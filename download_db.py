import subprocess
import sys
import base64
import binascii

# Configuration
CMD = [
    "railway", "ssh",
    "--project=9338b077-1b07-4b8c-94c6-80d955c025df",
    "--environment=d257012d-751c-4a37-995f-1c8b53cc4668",
    "--service=863f24c4-0482-4166-83cb-eadc03b8e984",
    "--", "base64", "/data/budget.db"
]

OUTPUT_FILE = "budget.db"

def download_db():
    print("⏳ Starting download of /data/budget.db (via Base64)...")
    
    try:
        # Run the command and capture stdout as bytes
        result = subprocess.run(CMD, capture_output=True, check=True, shell=True)
        
        # Decode base64 output
        # We need to clean up any potential SSH banner text (though using 'railway ssh -- cmd' usually avoids interactive shell banners, 
        # sometimes warnings appear). Base64 decoder will fail if there is garbage.
        # We'll rely on the fact that base64 output is usually the largest contiguous block of alphanumeric chars.
        
        raw_output = result.stdout
        
        # Simple cleanup: remove whitespace
        clean_output = raw_output.strip().replace(b'\r', b'').replace(b'\n', b'')
        
        # Decode
        decoded_data = base64.b64decode(clean_output)

        # Write to local file
        with open(OUTPUT_FILE, "wb") as f:
            f.write(decoded_data)
            
        print(f"✅ Success! Saved to {OUTPUT_FILE}")
        print(f"   Size: {len(decoded_data) / 1024:.2f} KB")
        
    except subprocess.CalledProcessError as e:
        print("❌ Error running Railway command:")
        print(e.stderr.decode('utf-8', errors='ignore'))
        
    except binascii.Error as e:
         print(f"❌ Error decoding Base64: {e}")
         print("   This means the server output contained non-base64 text (like an SSH banner).")
         
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    download_db()

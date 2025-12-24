import subprocess
import time

# Kill process on port 8000
try:
    result = subprocess.run(
        ['powershell', '-Command',
         'Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }'],
        capture_output=True,
        text=True
    )
    print(f"Kill command executed: {result.returncode}")
    print(f"Output: {result.stdout}")
    print(f"Error: {result.stderr}")

    time.sleep(2)

    # Verify
    result2 = subprocess.run(
        ['netstat', '-ano'],
        capture_output=True,
        text=True
    )

    if ':8000' in result2.stdout and 'LISTENING' in result2.stdout:
        print("Port 8000 still in use!")
        for line in result2.stdout.split('\n'):
            if ':8000' in line and 'LISTENING' in line:
                print(line)
    else:
        print("Port 8000 is now free!")

except Exception as e:
    print(f"Error: {e}")

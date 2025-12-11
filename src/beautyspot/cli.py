# src/beautyspot/cli.py

import sys
import os
import subprocess
import shutil


def main():
    args = sys.argv[1:]
    if not args or args[0] != "ui":
        print("Usage: beautyspot ui <path_to_db>")
        sys.exit(1)

    # ---  依存チェック ---
    if not shutil.which("streamlit"):
        print("❌ Streamlit not found.")
        print("Please install dashboard dependencies:")
        print("\n    pip install 'beautyspot[dashboard]'\n")
        sys.exit(1)

    if len(args) < 2:
        print(
            "Error: Please specify database path.\nExample: beautyspot ui ./my_project.db"
        )
        sys.exit(1)

    db_path = args[1]

    # dashboard.py の場所を特定
    import beautyspot

    package_dir = os.path.dirname(beautyspot.__file__)
    dashboard_script = os.path.join(package_dir, "dashboard.py")

    if not os.path.exists(dashboard_script):
        print(f"Error: dashboard.py not found at {dashboard_script}")
        sys.exit(1)

    print(f"🚀 Launching Dashboard for {db_path}...")

    # streamlit run ... -- --db path
    cmd = ["streamlit", "run", dashboard_script, "--", "--db", db_path]

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


if __name__ == "__main__":
    main()


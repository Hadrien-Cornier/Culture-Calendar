#!/usr/bin/env python3
"""
Pre-commit code quality checks and auto-fixes
Runs the same checks as GitHub Actions but locally before committing
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description="Running command", fix_mode=False):
    """Run a command and handle errors"""
    print(f"\n🔧 {description}")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if fix_mode:
            print("✅ Auto-fix applied successfully")
        else:
            print("✅ Check passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def install_dependencies():
    """Install required dependencies"""
    dependencies = [
        "black",  # Code formatting
    ]

    print("📦 Installing code quality dependencies...")
    for dep in dependencies:
        cmd = [sys.executable, "-m", "pip", "install", dep]
        if not run_command(cmd, f"Installing {dep}"):
            print(f"⚠️ Failed to install {dep} - continuing anyway")


def auto_fix_formatting():
    """Auto-fix code formatting with Black"""
    print("\n" + "=" * 60)
    print("🎨 AUTO-FIXING CODE FORMATTING")
    print("=" * 60)

    # Apply black formatting
    cmd = [
        "black",
        "src/",
        "tests/",
        "update_website_data.py",
        "pre_commit_checks.py",
        "test_validation.py",
        "run_tests.py",
    ]
    run_command(cmd, "Applying Black formatting", fix_mode=True)


def check_code_quality():
    """Run code quality checks (non-fixing)"""
    print("\n" + "=" * 60)
    print("🔍 RUNNING CODE QUALITY CHECKS")
    print("=" * 60)

    results = []

    # Check formatting (should pass after auto-fix)
    cmd = [
        "black",
        "--check",
        "--diff",
        "src/",
        "tests/",
        "update_website_data.py",
        "pre_commit_checks.py",
        "test_validation.py",
        "run_tests.py",
    ]
    results.append(("Black formatting", run_command(cmd, "Checking code formatting")))

    return results


def run_quick_tests():
    """Run quick unit tests"""
    print("\n" + "=" * 60)
    print("🧪 RUNNING QUICK TESTS")
    print("=" * 60)

    # Try to run quick tests if pytest is available
    try:
        pass

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-v",
            "--tb=short",
            "-m",
            "not live and not integration",
            "--maxfail=5",  # Stop after 5 failures
            "-x",  # Stop on first failure
        ]
        return run_command(cmd, "Running quick unit tests")
    except ImportError:
        print("⚠️ pytest not installed - skipping tests")
        return True


def check_git_status():
    """Check if there are any changes to commit"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        )
        if result.stdout.strip():
            print("\n📋 Files that will be included in commit:")
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
            return True
        else:
            print("\n⚠️ No changes to commit")
            return False
    except subprocess.CalledProcessError:
        print("\n⚠️ Not in a git repository")
        return True


def print_summary(results):
    """Print summary of all checks"""
    print("\n" + "=" * 60)
    print("📊 PRE-COMMIT CHECK SUMMARY")
    print("=" * 60)

    all_passed = True

    for check_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {check_name}")
        if not passed:
            all_passed = False

    print("-" * 60)

    if all_passed:
        print("🎉 All checks passed! Ready to commit.")
        print("\nNext steps:")
        print("  git add .")
        print("  git commit -m 'Your commit message'")
        return 0
    else:
        print("⚠️ Some checks failed!")
        print("\nPlease fix the issues above before committing.")
        print("You can run this script again after making fixes.")
        return 1


def main():
    """Main pre-commit check function"""
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("Usage: python pre_commit_checks.py [options]")
        print("Options:")
        print("  --fix-only    Only run auto-fixes, skip quality checks")
        print("  --check-only  Only run quality checks, skip auto-fixes")
        print("  --no-tests    Skip running tests")
        print("  --install     Install required dependencies")
        print("  --help, -h    Show this help")
        return 0

    fix_only = "--fix-only" in sys.argv
    check_only = "--check-only" in sys.argv
    no_tests = "--no-tests" in sys.argv
    install = "--install" in sys.argv

    # Change to project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)

    print("🎯 CULTURE CALENDAR PRE-COMMIT CHECKS")
    print("=" * 50)
    print(f"Working directory: {os.getcwd()}")

    if install:
        install_dependencies()
        return 0

    # Check git status
    has_changes = check_git_status()
    if not has_changes and not fix_only and not check_only:
        return 0

    # Install dependencies if needed
    try:
        pass
    except ImportError:
        print("📦 Required dependencies not found - installing...")
        install_dependencies()

    results = []

    # Auto-fixes (unless check-only mode)
    if not check_only:
        auto_fix_formatting()
        print("✅ Auto-fixes completed!")

    # Quality checks (unless fix-only mode)
    if not fix_only:
        quality_results = check_code_quality()
        results.extend(quality_results)

        # Quick tests (unless disabled)
        if not no_tests:
            test_result = run_quick_tests()
            results.append(("Quick tests", test_result))

    # Print summary
    if results:
        return print_summary(results)
    else:
        print(
            "\n✅ Auto-fixes completed! Remember to review changes before committing."
        )
        return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

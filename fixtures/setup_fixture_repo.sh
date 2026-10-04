#!/usr/bin/env bash
# Builds the test fixture repo at fixtures/conflict-repo. This repo is
# intentionally not committed to version control (a git repo nested
# inside another one causes problems -- see README), so this script
# recreates it instead. Run once before running tests:
#
#   bash fixtures/setup_fixture_repo.sh
#
# Safe to re-run -- it deletes and rebuilds the repo each time.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR/conflict-repo"

rm -rf "$REPO_DIR"
mkdir -p "$REPO_DIR/src"
cd "$REPO_DIR"

git init -q
git config user.email "fixture@example.com"
git config user.name "Fixture Repo"

cat > src/auth.js << 'EOF'
function login(username, password) {
  if (!username || !password) {
    return { success: false, error: "Missing credentials" };
  }

  const token = generateToken(username);
  return { success: true, token };
}

function generateToken(username) {
  return `token-for-${username}`;
}

module.exports = { login, generateToken };
EOF

git add src/auth.js
git commit -q -m "Initial commit: basic login function"
git branch -M main

# feature/oauth-login -- changes the generateToken call to add an OAuth provider
git checkout -q -b feature/oauth-login
sed -i.bak 's/const token = generateToken(username);/const token = generateOAuthToken(username, "google");/' src/auth.js
rm -f src/auth.js.bak
git commit -q -am "Use OAuth token generation in login()"

# fix/session-timeout -- changes the SAME line, differently, from main
git checkout -q main
git checkout -q -b fix/session-timeout
sed -i.bak 's/const token = generateToken(username);/const token = generateToken(username, { expiresInMinutes: 30 });/' src/auth.js
rm -f src/auth.js.bak
git commit -q -am "Add session timeout to generated tokens"

# chore/add-comment -- touches the same file but a different, non-conflicting line
git checkout -q main
git checkout -q -b chore/add-comment
sed -i.bak '1i // Handles user authentication for the app' src/auth.js
rm -f src/auth.js.bak
git commit -q -am "Add file header comment"

git checkout -q main

echo "Fixture repo built at $REPO_DIR"

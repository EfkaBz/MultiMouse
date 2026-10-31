#!/bin/sh
# Create the self-signed "MultiMouse Code Signing" certificate in the login keychain (once per Mac).
#
#     sh tools/make_mac_cert.sh
#
# build.py signs MultiMouse.app with it: macOS then recognises every new build as the same app,
# so Accessibility / Input Monitoring stay granted after an update.
set -e
NAME="MultiMouse Code Signing"
if security find-identity -p codesigning | grep -q "\"$NAME\""; then
    echo "Certificat « $NAME » déjà présent."
    exit 0
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/cs.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $NAME
[ext]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
EOF
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TMP/key.pem" -out "$TMP/cert.pem" -days 3650 -config "$TMP/cs.cnf"
PASS=$(openssl rand -hex 12)
openssl pkcs12 -export -legacy -inkey "$TMP/key.pem" -in "$TMP/cert.pem" -out "$TMP/id.p12" -passout "pass:$PASS" 2>/dev/null \
    || openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" -out "$TMP/id.p12" -passout "pass:$PASS"
security import "$TMP/id.p12" -k "$HOME/Library/Keychains/login.keychain-db" -P "$PASS" -T /usr/bin/codesign
echo "Certificat « $NAME » créé."

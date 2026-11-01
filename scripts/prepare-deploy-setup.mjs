import { readFileSync, writeFileSync } from 'node:fs'
// Windows checkouts may use CRLF; the embedded executable must always use LF.
const receiver = Buffer.from(readFileSync('scripts/server-deploy.py', 'utf8').replace(/\r\n?/g, '\n')).toString('base64').match(/.{1,100}/g).join('\n')
const setup = `#!/usr/bin/env bash
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'Execute com sudo bash.'; exit 1; }
for cmd in python3 curl ssh-keygen base64 useradd visudo install; do command -v "$cmd" >/dev/null; done
[[ -d /home/mercaflor.clicpic.co && ! -L /home/mercaflor.clicpic.co ]] || exit 1
[[ -d /home/mercaflor.clicpic.co/public_html ]] || exit 1
site_owner=$(stat -Lc '%U' /home/mercaflor.clicpic.co/public_html)
[[ "$site_owner" =~ ^[a-z_][a-z0-9_-]*$ && "$site_owner" != root ]] || { echo 'Confirmar o usuario proprietario de public_html antes de instalar.'; exit 1; }
getent passwd "$site_owner" >/dev/null
printf '%s\\n' "$site_owner" > /etc/mercaflor-concierge-owner
chown root:root /etc/mercaflor-concierge-owner
chmod 0644 /etc/mercaflor-concierge-owner
getent group nogroup >/dev/null
[[ -f /etc/ssh/ssh_host_ed25519_key.pub ]] || { echo 'Ed25519 server host key missing'; exit 1; }
receiver=$(mktemp)
trap 'rm -f -- "$receiver"' EXIT
base64 -d > "$receiver" <<'CLICPIC_RECEIVER'
${receiver}
CLICPIC_RECEIVER
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$receiver"
install -o root -g root -m 0755 "$receiver" /usr/local/sbin/mercaflor-concierge-deploy
if ! id cpmercaflordeploy >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/cpmercaflordeploy --shell /bin/bash cpmercaflordeploy
fi
[[ "$(getent passwd cpmercaflordeploy | cut -d: -f6)" == /var/lib/cpmercaflordeploy ]] || { echo 'Unexpected deploy account home'; exit 1; }
install -d -o root -g root -m 0755 /var/lib/cpmercaflordeploy /var/lib/cpmercaflordeploy/.ssh
install -d -o ubuntu -g ubuntu -m 0700 /home/ubuntu/.ssh
if [[ ! -f /home/ubuntu/.ssh/mercaflor-concierge-github ]]; then
  sudo -u ubuntu ssh-keygen -q -t ed25519 -N '' -C mercaflor-concierge-github -f /home/ubuntu/.ssh/mercaflor-concierge-github
fi
key=$(cat /home/ubuntu/.ssh/mercaflor-concierge-github.pub)
[[ "$key" == "ssh-ed25519 "* ]] || { echo 'Invalid deployment public key'; exit 1; }
python3 - <<'CLICPIC_AUTHORIZATION'
import json
from pathlib import Path
key = Path('/home/ubuntu/.ssh/mercaflor-concierge-github.pub').read_text().strip()
command = 'sudo -n /usr/local/sbin/mercaflor-concierge-deploy "$SSH_ORIGINAL_COMMAND"'
line = 'restrict,command=' + json.dumps(command) + ' ' + key + '\\n'
Path('/var/lib/cpmercaflordeploy/.ssh/authorized_keys').write_text(line)
CLICPIC_AUTHORIZATION
chown root:root /var/lib/cpmercaflordeploy/.ssh/authorized_keys
chmod 0644 /var/lib/cpmercaflordeploy/.ssh/authorized_keys
printf '%s\\n' 'cpmercaflordeploy ALL=(root) NOPASSWD: /usr/local/sbin/mercaflor-concierge-deploy' > /etc/sudoers.d/mercaflor-concierge-deploy
chmod 0440 /etc/sudoers.d/mercaflor-concierge-deploy
visudo -cf /etc/sudoers.d/mercaflor-concierge-deploy
install -d -o root -g root -m 0700 /home/mercaflor.clicpic.co/.deploy-backups
stamp=$(date +%s)
if [[ -e /home/mercaflor.clicpic.co/public_html/BKP || -L /home/mercaflor.clicpic.co/public_html/BKP ]]; then
  mv -- /home/mercaflor.clicpic.co/public_html/BKP "/home/mercaflor.clicpic.co/.deploy-backups/BKP-$stamp"
fi
shopt -s nullglob
for archive in /home/mercaflor.clicpic.co/public_html/*.zip; do
  [[ -f "$archive" && ! -L "$archive" ]] || continue
  mv -- "$archive" "/home/mercaflor.clicpic.co/.deploy-backups/$stamp-$(basename "$archive")"
done
/usr/local/sbin/mercaflor-concierge-deploy probe
echo 'HOST_KEY_PUBLICA (para a variavel DEPLOY_HOST_KEY):'
cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub
echo 'INSTALADO. A versao ativa do site ainda nao foi substituida.'
echo 'A chave privada ficou em /home/ubuntu/.ssh/mercaflor-concierge-github; nao envie no chat.'
`
writeFileSync('deployment/setup-deploy.sh', setup)
console.log('Generated deployment/setup-deploy.sh (no private keys included).')

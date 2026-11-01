# Deploy — mercaflor.clicpic.co

Prepared from Mesa’s restricted SSH deployment workflow, using a separate account, key, receiver and site directory. Not installed on the server yet.

1. Confirm CyberPanel website root is `/home/mercaflor.clicpic.co/public_html`, with the correct non-root site owner, DNS and valid HTTPS. Installer expects the server’s existing `ubuntu` user and `nogroup` group, like Mesa.
2. Review `deployment/setup-deploy.sh`. Upload it OUTSIDE public_html, then run it with sudo on the server. It provisions `cpmercaflordeploy`, an exclusive SSH key, and a restricted receiver supporting probe/deploy/rollback. It preserves the active site. Do not reuse Mesa credentials.
3. GitHub repository Variables: `DEPLOY_HOST` = real origin server IP; `DEPLOY_HOST_KEY` = public Ed25519 host key printed by installer; `DEPLOY_ENABLED` = `false` until setup is verified.
4. Repository Secret `DEPLOY_SSH_KEY`: enter the dedicated key from `/home/ubuntu/.ssh/mercaflor-concierge-github` directly in GitHub Secrets, never in chat or commits.
5. After setup verification, set `DEPLOY_ENABLED=true` and run the workflow. Future pushes to main validate, build and deploy atomically. HTTPS verification failure rolls back to the prior release.

Server rollback: `sudo /usr/local/sbin/mercaflor-concierge-deploy rollback`.

Creating the DNS subdomain alone does not install the deployment receiver or configure GitHub secrets. The landing-page test site is separate and is not modified by this workflow.

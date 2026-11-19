# SPDX-License-Identifier: GPL-2.0-or-later
"""Install/recover the exact connection-options candidate on this head unit."""
from pathlib import Path
import argparse
import base64
import getpass
import hashlib
import json
import socket
import sys
import uuid

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0,str(PACKAGE))
import options_upgrade as upgrade
import label_deploy


def connect(direct):
    import paramiko
    class Pinned(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self,client,host,key):
            actual='SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
            if actual != label_deploy.PIN: raise RuntimeError('Head-unit key differs; login refused')
    client=paramiko.SSHClient()
    client.set_missing_host_key_policy(Pinned())
    sock=None
    password=getpass.getpass('Head-unit root password: ')
    try:
        if not direct: sock=socket.create_connection(('127.0.0.1',6969),timeout=8)
        client.connect('169.254.199.99',sock=sock,username='root',password=password,
                       look_for_keys=False,allow_agent=False,timeout=10,banner_timeout=10,auth_timeout=15)
        return client
    except Exception:
        client.close()
        if sock: sock.close()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['verify-package','preflight','status','install','restore'])
    parser.add_argument('--direct',action='store_true',help='Use HU port 22 instead of the existing laptop port-6969 proxy')
    args=parser.parse_args()
    manifest=upgrade.load_package(PACKAGE)
    if args.action=='verify-package':
        print('Connection-options package payload hashes verified. No connection made.')
        return
    client=connect(args.direct)
    remote=label_deploy.Remote(client)
    result={'action':args.action,'authorizedWorkflows':[],'accessedWorkflows':[]}
    try:
        if args.action in ('install','restore'):
            remote.prepare_sync((PACKAGE/'aa-label-sync').read_bytes())
        if args.action=='preflight':
            result['preflight']=upgrade.preflight(remote)
        elif args.action=='install':
            backup=PACKAGE/('backup-'+uuid.uuid4().hex)
            result['journal']=upgrade.install(remote,PACKAGE,backup)
            result['localBackup']=str(backup)
            result['message']='Independent settings installed; connection/tile preferences preserved, auto-open OFF. Restart iDrive normally while parked.'
        elif args.action=='restore':
            journal=upgrade.optional(remote,upgrade.JOURNAL)
            if journal is None: raise RuntimeError('No background upgrade journal')
            result['message']=upgrade.restore(remote,manifest,json.loads(journal))
        result['files']={}
        for name,path in upgrade.TARGETS.items():
            data,info=remote.snapshot(path)
            digest=upgrade.sha(data)
            result['files'][name]={'sha256':digest,**info,
                'matches': 'options' if digest==manifest['after'][name] else 'previous' if digest==upgrade.BEFORE[name] else 'unknown'}
        result['autoConnectEnabled']=remote.exists(upgrade.AUTO) or remote.exists('/opt/aa/autostart')
        result['autoOpenEnabled']=remote.exists(upgrade.OPEN) or remote.exists('/opt/aa/auto-open')
        result['tileEnabled']=remote.exists(upgrade.TILE)
        result['aaState']=(upgrade.optional(remote,'/dev/shmem/nbt-aad-state') or b'').decode(errors='replace').strip()
        (PACKAGE/('live-'+args.action+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:
        try: remote.cleanup_sync()
        finally: client.close()


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('STOP:',str(error),file=sys.stderr)
        sys.exit(1)

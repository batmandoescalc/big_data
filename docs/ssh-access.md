# SSH Access Guide

This guide describes the access pattern without publishing student identifiers,
keys, IP addresses, or internal server details. Obtain the current hostnames and
authorization from the project supervisor.

## Prerequisites

1. Connect through the network access method approved by UConn. During the
   on-campus setup used for this project, this was the `UConn-Secure` Wi-Fi
   network.
2. Confirm that the student's regular NetID has been granted access to the VMs.
3. Open PowerShell in the VS Code integrated terminal.
4. Substitute the assigned NetID and hostname for the placeholders below.

## First login

```powershell
ssh YOUR_NETID@CONTROLLER_HOST
```

On first contact, verify the server's host-key fingerprint through an approved
source before accepting it. Complete password and Duo authentication when
prompted. After login, verify the destination:

```bash
whoami
hostname -f
```

Use `exit` to return to the local PowerShell terminal.

## Dedicated SSH key

Generate a named key so it does not overwrite an existing default key:

```powershell
ssh-keygen -t rsa -b 4096 -f "$env:USERPROFILE\.ssh\id_rsa_uconn_hadoop" -C "uconn-hadoop"
```

This creates two files:

- `id_rsa_uconn_hadoop`: private key; never share or commit it.
- `id_rsa_uconn_hadoop.pub`: public key; install this on authorized servers.

Copy the public key to a server using the procedure approved by UConn. Then test
explicitly with the dedicated private key:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_rsa_uconn_hadoop" YOUR_NETID@CONTROLLER_HOST
```

Repeat the approved public-key installation for each worker VM. Installing a key
on one node does not automatically authorize it on the other nodes.

## Common outcomes

- `Permission denied`: confirm that the NetID was granted access and that the
  correct account and key were selected.
- Connection timeout: confirm network access and the current hostname.
- Host-key warning: do not bypass it automatically; verify whether the server was
  rebuilt or its key legitimately changed.
- Too many authentication failures: select the intended key explicitly with
  `ssh -i` and contact an administrator if the problem persists.

## Information that must remain private

Do not commit passwords, Duo codes, private keys, public keys tied to a person,
NetIDs, authentication transcripts, server fingerprints, or internal IP
addresses. Server administrators may retain connection and activity logs.

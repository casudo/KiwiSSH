# Supported OS/Device Types

| Vendor            | OS/Device Type        | YAML file                                                                        | Notes                                                              |
| ----------------- | --------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 6WIND             | VSR                   | [6wind_vsr.yaml](/backend/config/vendors/6wind_vsr.yaml)                         |                                                                    |
| A10 Networks      | A10 ACOS              | [a10_acos.yaml](/backend/config/vendors/a10_acos.yaml)                           |                                                                    |
| Accedian Networks | AEN                   | [accedian_aen.yaml](/backend/config/vendors/accedian_aen.yaml)                   | Accedian Performance Elements (NIDs)                               |
| Acme Packet       | Acme Packet           | [acmepacket_acmepacket.yaml](/backend/config/vendors/acmepacket_acmepacket.yaml)           |                                                                    |
| AddPack            | AddPack               | [addpack_addpack.yaml](/backend/config/vendors/addpack_addpack.yaml)             |                                                                    |
| Adtran            | Total Access (AOS)                   | [adtran_aos.yaml](/backend/config/vendors/adtran_aos.yaml)                       |                                |
| Adtran            | ADVA                   | [adtran_adva.yaml](/backend/config/vendors/adtran_adva.yaml)                     | [ADVA](#adtran-adva)       |
| Alcatel-Lucent    | AOS                   | [alcatel_aos.yaml](/backend/config/vendors/alcatel_aos.yaml)                     | AOS6 - vxworks-based                                               |
| Alcatel-Lucent    | AOS7                  | [alcatel_aos7.yaml](/backend/config/vendors/alcatel_aos7.yaml)                   | AOS7 and AOS8 - Linux-based                                        |
| Alcatel-Lucent    | ISAM                  | [alcatel_isam.yaml](/backend/config/vendors/alcatel_isam.yaml)                   |                                                                    |
| Alcatel-Lucent    | SROS                  | [alcatel_sros.yaml](/backend/config/vendors/alcatel_sros.yaml)                   | Formerly TiMOS                                                     |
| Alcatel-Lucent    | Wireless              | [aruba_aosw.yaml](/backend/config/vendors/aruba_aosw.yaml)                       | Same model as Arube Wireless (AOS-W)                               |
| Allied Telesis | Alliedware Plus | [alliedtelesis_awplus.yaml](/backend/config/vendors/alliedtelesis_awplus.yaml) |                  |
| Allied Telesis | PowerConnect | [alliedtelesis_powerconnect.yaml](/backend/config/vendors/alliedtelesis_powerconnect.yaml) | AT-8000S, AT-8000GS series                 |
| Arbor Networks     | ArbOS                 | [arbornetworks_arbos.yaml](/backend/config/vendors/arbornetworks_arbos.yaml)     |                                                                   |
| Arista            | EOS                   | [arista_eos.yaml](/backend/config/vendors/arista_eos.yaml)                       |                                                                    |
| Aruba             | AOS-CX                | [aruba_aoscx.yaml](/backend/config/vendors/aruba_aoscx.yaml)                     | [AOS-CX](#hpe-aruba-networking)                                    |
| Aruba             | AOS-W                 | [aruba_aosw.yaml](/backend/config/vendors/aruba_aosw.yaml)                       | [AOS-W](#hpe-aruba-networking)                                     |
| Aruba             | IAP/Instant           | [aruba_iap.yaml](/backend/config/vendors/aruba_iap.yaml)                         | [Aruba Instant](#hpe-aruba-networking)                             |
| Asterfusion | AsterNOS | [asterfusion_asternos.yaml](/backend/config/vendors/asterfusion_asternos.yaml) | |
| AudioCodes | AudioCodes | [audiocodes_audiocodes.yaml](/backend/config/vendors/audiocodes_audiocodes.yaml) | AudioCodes Mediant devices version > 7.0 |
| AudioCodes | MediaPack | [audiocodes_mediapack.yaml](/backend/config/vendors/audiocodes_mediapack.yaml) | MediaPack MP1xx and Mediant 1000 devices (firmware v4.xx, v5.xx, v6.xx) |
| BDCOM | BDCOM | [bdcom_bdcom.yaml](/backend/config/vendors/bdcom_bdcom.yaml) | BDCOM S2200PB, S2200-B, S2500-B, S2500-C, S2500PB, S2500-P, S2900 series |
| Brocade | FabricOS | [brocade_fabricos.yaml](/backend/config/vendors/brocade_fabricos.yaml) |  |
| Brocade | Enhanced FabricOS | [brocade_efos.yaml](/backend/config/vendors/brocade_efos.yaml) |  |
| Brocade | FastIron | [brocade_fastiron.yaml](/backend/config/vendors/brocade_fastiron.yaml) |  |
| Brocade | IronWare | [brocade_ironware.yaml](/backend/config/vendors/brocade_ironware.yaml) |  |
| Brocade | NOS (Network Operating System) | [brocade_nos.yaml](/backend/config/vendors/brocade_nos.yaml) |  |
| Brocade | 6910 | [brocade_6910.yaml](/backend/config/vendors/brocade_6910.yaml) |  |
| Brocade | SLX-OS | [brocade_slxos.yaml](/backend/config/vendors/brocade_slxos.yaml) |  |
| Brocade           | Vyatta                | [brocade_vyatta.yaml](/backend/config/vendors/brocade_vyatta.yaml)               | Also used for Vyos <= 1.2.x, for newer versions use the VyOS model |
| Calix | AXOS | [calix_axos.yaml](/backend/config/vendors/calix_axos.yaml) | |
| Cambium | Cambium ePMP | [cambium_epmp.yaml](/backend/config/vendors/cambium_epmp.yaml) | ePMP series |
| Casa              | Casa                  | [casa_casa.yaml](/backend/config/vendors/casa_casa.yaml)                         |                                                                    |
| Centec Networks | CNOS | [centec_cnos.yaml](/backend/config/vendors/centec_cnos.yaml) | |
| Check Point | GaiaOS | [checkpoint_gaiaos.yaml](/backend/config/vendors/checkpoint_gaiaos.yaml) | |
| Ciena | SAOS | [ciena_saos.yaml](/backend/config/vendors/ciena_saos.yaml) | Used for 6.x |
| Ciena | SAOS 10 | [ciena_saos10.yaml](/backend/config/vendors/ciena_saos10.yaml) | Used for 10.x |
| Cisco             | ACS                   | [cisco_acs.yaml](/backend/config/vendors/cisco_acs.yaml)                         |                                                                    |
| Cisco             | AireOS                | [cisco_aireos.yaml](/backend/config/vendors/cisco_aireos.yaml)                   | [AireOS](#cisco-aireos)                                            |
| Cisco             | IOS                   | [cisco_ios.yaml](/backend/config/vendors/cisco_ios.yaml)                         |                                                                    |
| Cisco             | IOS-XR                | [cisco_iosxr.yaml](/backend/config/vendors/cisco_iosxr.yaml)                     |                                                                    |
| Cisco             | NXOS                  | [cisco_nxos.yaml](/backend/config/vendors/cisco_nxos.yaml)                       |                                                                    |
| Cisco             | ASA                   | [cisco_asa.yaml](/backend/config/vendors/cisco_asa.yaml)                         |                                                                    |
| Cisco | AsyncOS | [cisco_asyncos.yaml](/backend/config/vendors/cisco_asyncos.yaml) | |
| Cisco | CatOS | [cisco_catos.yaml](/backend/config/vendors/cisco_catos.yaml) | |
| Cisco | ExaLink Fusion (Nexus 3550-F) | [cisco_exalink.yaml](/backend/config/vendors/cisco_exalink.yaml) | [Cisco ExaLink](#cisco-nexus-3550-f-exalink-fusion) |
| Cisco | NGA | [cisco_nga.yaml](/backend/config/vendors/cisco_nga.yaml) | |
| Cisco | SMA | [cisco_sma.yaml](/backend/config/vendors/cisco_sma.yaml) |  |
| Cisco | SMB (Nikola series) | [cisco_smb.yaml](/backend/config/vendors/cisco_smb.yaml) |  |
| Cisco | UCS | [cisco_ucs.yaml](/backend/config/vendors/cisco_ucs.yaml) | |
| Cisco | Viptela | [cisco_viptela.yaml](/backend/config/vendors/cisco_viptela.yaml) | |
| Citrix            | NetScaler             | [citrix_netscaler.yaml](/backend/config/vendors/citrix_netscaler.yaml)           |                                                                    |
| Coriant (former Tellabs) | TMOS (8800) | [coriant_tmos.yaml](/backend/config/vendors/coriant_tmos.yaml) | |
| Coriant (former Tellabs) | 8600 | [coriant_8600.yaml](/backend/config/vendors/coriant_8600.yaml) | |
| Coriant (former Tellabs) | Groove | [coriant_groove.yaml](/backend/config/vendors/coriant_groove.yaml) | |
| ComNet | Microsemi Switch | [comnet_ms.yaml](/backend/config/vendors/comnet_ms.yaml) | |
| Comtrol | RocketLinx | [comtrol_rocketlinx.yaml](/backend/config/vendors/comtrol_rocketlinx.yaml) | |
| Cumulus | Linux | [cumulus_linux.yaml](/backend/config/vendors/cumulus_linux.yaml) | [Cumulus Linux](#cumulus-linux) |
| Datacom | Datacom | [datacom_datacom.yaml](/backend/config/vendors/datacom_datacom.yaml) | For DmSwitch 3000 |
| DCN | DCN | [cisco_ios.yaml](/backend/config/vendors/cisco_ios.yaml) | Same model as Cisco IOS |
| DELL | PowerConnect | [dell_powerconnect.yaml](/backend/config/vendors/dell_powerconnect.yaml) | |
| DELL | AOSW | [aruba_aosw.yaml](/backend/config/vendors/aruba_aosw.yaml) | Same model as Aruba Wireless (AOSW) |
| DELL | Dell X-Series | [dell_dellx.yaml](/backend/config/vendors/dell_dellx.yaml) | |
| DELL | EMC Networking OS6 | [dell_os6.yaml](/backend/config/vendors/dell_os6.yaml) | |
| DELL | EMC Networking OS10 | [dell_os10.yaml](/backend/config/vendors/dell_os10.yaml) | [Dell EMC Networking OS10](#dell-emc-networking-os10) |
| D-Link            | D-Link                | [dlink_dlink.yaml](/backend/config/vendors/dlink_dlink.yaml)                     |                                                                    |
| D-Link            | D-Link NextGen        | [dlink_dlinknextgen.yaml](/backend/config/vendors/dlink_dlinknextgen.yaml)       | Cisco-like CLI                                                     |
| ECI Telecom | ECIapollo | [ecitelecom_eciapollo.yaml](/backend/config/vendors/ecitelecom_eciapollo.yaml) | |
| Eltex             | Eltex                 | [eltex_eltex.yaml](/backend/config/vendors/eltex_eltex.yaml)                     |                                                                    |
| Extreme Networks  | WM                    | [motorola_rfs.yaml](/backend/config/vendors/motorola_rfs.yaml)                   | Uses Motorola's RFS vendor file                                    |
| Extreme Networks  | EXOS                  | [extreme_exos.yaml](/backend/config/vendors/extreme_exos.yaml)                   |                                                                    |  
| Extreme Networks  | VOSS                  | [extreme_voss.yaml](/backend/config/vendors/extreme_voss.yaml)                   |                                                                    |
| Fortinet          | FortiGate             | [fortinet_fortigate.yaml](/backend/config/vendors/fortinet_fortigate.yaml)       | [FortiGate](#fortinet-device-types)                                |
| Fortinet          | FortiOS               | [fortinet_fortios.yaml](/backend/config/vendors/fortinet_fortios.yaml)           | [FortiOS](#fortinet-device-types)                                  |
| Fortinet          | FortiWLC              | [fortinet_wlc.yaml](/backend/config/vendors/fortinet_wlc.yaml)                   |                                                                    |
| HP                | ProCurve              | [hp_procurve.yaml](/backend/config/vendors/hp_procurve.yaml)                     |                                                                    |
| Huawei                | Versatile Routing Platform       | [huawei_vrp.yaml](/backend/config/vendors/huawei_vrp.yaml)                     |                                                                    |
| Juniper           | JunOS                 | [juniper_junos.yaml](/backend/config/vendors/juniper_junos.yaml)                 | [JunOS](#juniper-junos)                                            |
| Mikrotik          | RouterOS              | [mikrotik_routeros.yaml](/backend/config/vendors/mikrotik_routeros.yaml)         | [RouterOS](#mikrotik-routeros)                                     |
| Motorola          | RFS                   | [motorola_rfs.yaml](/backend/config/vendors/motorola_rfs.yaml)                   |                                                                    |
| OpenWRT           |                       | [openwrt.yaml](/backend/config/vendors/openwrt.yaml)                             |                                                                    |
| OPNsense          |                       | [opnsense.yaml](/backend/config/vendors/opnsense.yaml)                           |                                                                    |
| Palo Alto         | PanOS                 | [paloalto_panos.yaml](/backend/config/vendors/paloalto_panos.yaml)               |                                                                    |
| Perle             | IOLAN Console Servers | [perle_iolan.yaml](/backend/config/vendors/perle_iolan.yaml)                     |                                                                    |
| pfSense           |                       | [pfsense.yaml](/backend/config/vendors/pfsense.yaml)                             |                                                                    |
| SONiC             | Enterprise SONiC      | [sonic_enterprise.yaml](/backend/config/vendors/sonic_enterprise.yaml)           |                                                                    |
| TrueNAS           |                       | [truenas.yaml](/backend/config/vendors/truenas.yaml)                             | [TrueNAS](#truenas)                                                |
| Ubiquiti          | UniFi                 | [ubiquiti_unifi.yaml](/backend/config/vendors/ubiquiti_unifi.yaml)               | [Ubiquiti](#ubiquiti)                                              |
| VyOS Networks     | VyOS                  | [vyos_vyos.yaml](/backend/config/vendors/vyos_vyos.yaml)                         | Fork of Vyatta, tracking the supported versions (>= 1.4.x)         |
| Watchguard        | FirewareOS            | [watchguard_firewareos.yaml](/backend/config/vendors/watchguard_firewareos.yaml) |
| Westermo          | WeOS                  | [westermo_weos.yaml](/backend/config/vendors/westermo_weos.yaml)                 |                                                                    |

---

## Adtran ADVA

To ensure KiwiSSH can fetch the configuration, you have to make sure that `cli-paging` is set to `disabled` for the user that is used to connect to the ADVA devices.

### Restoring the configuration

In order to trick the device into restoring the files you need to add the following remarks as first line of the file.

```
# DO NOT EDIT THIS LINE. FILE_TYPE=CONFIGURATION_FILE
```

## Cisco AireOS

**Cisco WLC Configuration**
Create a user with read-write privilege:

`mgmtuser add kiwissh **** read-write`

KiwiSSH needs read-write privilege in order to execute `config paging disable`.

## Cisco Nexus 3550-F (ExaLink Fusion)

The Cisco Nexus 3550-F (formerly Exablaze ExaLink Fusion) is an ultra-low-latency Layer 1/2 switch platform based on FPGA technology, primarily used in high-frequency trading and HPC environments. It runs a custom Linux-based OS with a proprietary CLI and JSON RPC API.

### Device Configuration

Create a read-only user for KiwiSSH on the device:

```bash
admin@N3550-F> configure user kiwissh password <password>
admin@N3550-F> configure user kiwissh privilege read-only
```

## Cumulus Linux

With the release of Cumulus Linux 3.4.0 the platform moved the routing daemon to a fork of `Quagga` named `FRRouting`. See the below link for the release notes.

[https://support.cumulusnetworks.com/hc/en-us/articles/115011217808-Cumulus-Linux-3-4-0-Release-Notes](https://support.cumulusnetworks.com/hc/en-us/articles/115011217808-Cumulus-Linux-3-4-0-Release-Notes)

Comment out the inappropriate commands in the [cumulus_linux.yaml](/backend/config/vendors/cumulus_linux.yaml) file to avoid errors when collecting the configuration.

> [!NOTE]
> The default command set for the Cumulus Linux Vendor file is `frr` and `NCLU`.

## Dell EMC Networking OS10

Disable banner/motd

```text
banner login disable
banner motd disable
```

Add allowed commands to privilege level 4

```text
privilege exec priv-lvl 4 "show inventory"
privilege exec priv-lvl 4 "show inventory media"
privilege exec priv-lvl 4 "show running-configuration"
```

Create the user will the role sysadmin (it will see the full config, including auth info and users) and the privilege level 4

```text
username kiwissh password verysecurepassword role sysadmin priv-lvl 4
```

## Fortinet device types

There are two models for Fortinet devices:

- `fortigate`: for the FortiGate firewalls
- `fortios`: for VM-Based appliances (FortiManager, FortiADC, FortiAnalyzer...)

### Notes for both device types

#### Configuration changes / hiding passwords

FortiGate and FortiOS re-encrypt their passwords every time the configuration is shown. This results in a lot of apparent configuration changes on every pull.

To avoid this, enable the redaction feature inside the vendor YAML file (`redaction.enabled: true`). This will replace all passwords with a fixed string, so the configuration will only change when there are actual changes to the configuration.

## HPE Aruba Networking

HPE Aruba offers various networking devices with different operating systems.

### HPE Aruba Networking Instant Mode (Aruba Instant)

[Aruba Instant](https://arubanetworking.hpe.com/techdocs/ArubaDocPortal/content/cons-instant-home.htm) runs on IAPs (Instant Access points).

KiwiSSH uses [aruba_iap.yaml](/backend/config/vendors/aruba_iap.yaml). When run on the virtual WLAN controller, it will also collect the list of the WLAN-AP linked to the controller.

The aosw model for AOS 8 used to be used for Aruba Instant, but it does not work as well and may stop working in the future.

### HPE Aruba Networking Wireless Operating System 8 (AOS 8)

[AOS 8](https://arubanetworking.hpe.com/techdocs/ArubaDocPortal/content/cons-aos-home.htm) runs on WLAN controllers (mobility controllers) and controller-managed access points.

Use [aruba_aosw.yaml](/backend/config/vendors/aruba_aosw.yaml).

### HPE Aruba Networking CX Switch Operating System (AOS-CX)

[AOS-CX](https://arubanetworking.hpe.com/techdocs/AOS-CX/help_portal/Content/home.htm) is the operating system for the newer CX-Series.

Use [aruba_aoscx.yaml](/backend/config/vendors/aruba_aoscx.yaml).

## Juniper JunOS

In order to be able to reach the devices via SSH, follow the steps below:

Create login class `cfg-view`:

```bash
set system login class cfg-view permissions view-configuration
set system login class cfg-view allow-commands "(show)|(set cli screen-length)|(set cli screen-width)"
set system login class cfg-view deny-commands "(clear)|(file)|(file show)|(help)|(load)|(monitor)|(op)|(request)|(save)|(set)|(start)|(test)"
set system login class cfg-view deny-configuration all
```

Create a user with `cfg-view` class set:

```bash
set system login user kiwissh class cfg-view
set system login user kiwissh authentication plain-text-password "yourpasswordhere"
```

## MikroTik RouterOS

RouterOS 7.12 and later support ED25519 keys.

Create a key pair, save the public key (id_ed25519.pub) and save it on flash. Create a user and attach the public key.

```bash
[admin@mikrotik] > /user add name=kiwissh group=read disabled=no
[admin@mikrotik] > /user ssh-keys import public-key-file=id_ed25519.pub user=kiwissh
```

KiwiSSH can now retrieve your configuration!

## TrueNAS

The TrueNAS vendor YAML file currently uses the `sqlite3` command without `sudo` to fetch the configuration from the database. For TrueNAS SCALE machines, make sure the user you use to connect can run this command, or if needed, with passwordless `sudo`. Add the following to your sudoers file via `sudo visudo`:

`kiwissh ALL=(ALL) NOPASSWD: /usr/bin/sqlite3 file\:///data/freenas-v1.db?mode\=ro&immutable\=1 .dump`

## Ubiquiti

In order to be able to reach the devices via SSH, follow the steps below:

> [!NOTE]
> Based on UniFi Network v10.2.105

1. Go to "UniFi Devices"
2. In the bottom left corner click on "Device Updates and Settings"
3. Extand "Device SSH Settings" at the bottom of the side panel
4. Check "Device SSH Authentication"
5. Document the SSH username and password you set here in the kiwissh config file for the device(s) you want to backup

> [!WARNING]
> In order to connect to the Gateway, you'll need to enable SSH access via the Control Plane.

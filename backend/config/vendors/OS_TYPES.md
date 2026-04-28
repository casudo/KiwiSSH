# Supported OS/Device Types

| Vendor       | OS/Device Type        | YAML file                                                                        | Notes                                  |
| ------------ | --------------------- | -------------------------------------------------------------------------------- | -------------------------------------- |
| A10 Networks | A10 ACOS              | [a10_acos.yaml](/backend/config/vendors/a10_acos.yaml)                           |                                        |
| Arista       | EOS                   | [arista_eos.yaml](/backend/config/vendors/arista_eos.yaml)                       |                                        |
| Aruba        | AOS-CX                | [aruba_aoscx.yaml](/backend/backend/config/vendors/aruba_aoscx.yaml)             | [AOS-CX](#hpe-aruba-networking)        |
| Aruba        | AOS-W                 | [aruba_aosw.yaml](/backend/config/vendors/aruba_aosw.yaml)                       | [AOS-W](#hpe-aruba-networking)         |
| Aruba        | IAP/Instant           | [aruba_iap.yaml](/backend/config/vendors/aruba_iap.yaml)                         | [Aruba Instant](#hpe-aruba-networking) |
| Casa         | Casa                  | [casa_casa.yaml](/backend/config/vendors/casa_casa.yaml)                         |                                        |
| Cisco        | AireOS                | [cisco_aireos.yaml](/backend/config/vendors/cisco_aireos.yaml)                   | [AireOS](#cisco-aireos)                |
| Cisco        | IOS                   | [cisco_ios.yaml](/backend/config/vendors/cisco_ios.yaml)                         |                                        |
| Cisco        | NXOS                  | [cisco_nxos.yaml](/backend/config/vendors/cisco_nxos.yaml)                       |                                        |
| Citrix       | NetScaler             | [citrix_netscaler.yaml](/backend/config/vendors/citrix_netscaler.yaml)           |                                        |
| Fortinet     | FortiGate             | [fortinet_fortigate.yaml](/backend/config/vendors/fortinet_fortigate.yaml)       | [FortiGate](#fortinet-device-types)    |
| Fortinet     | FortiOS               | [fortinet_fortios.yaml](/backend/config/vendors/fortinet_fortios.yaml)           | [FortiOS](#fortinet-device-types)      |
| HP           | ProCurve              | [hp_procurve.yaml](/backend/config/vendors/hp_procurve.yaml)                     |                                        |
| Juniper      | JunOS                 | [juniper_junos.yaml](/backend/config/vendors/juniper_junos.yaml)                 | [JunOS](#juniper-junos)                |
| OpenWRT      |                       | [openwrt.yaml](/backend/config/vendors/openwrt.yaml)                             |                                        |
| OPNsense     |                       | [opnsense.yaml](/backend/config/vendors/opnsense.yaml)                           |                                        |
| Palo Alto    | PanOS                 | [paloalto_panos.yaml](/backend/config/vendors/paloalto_panos.yaml)               |                                        |
| Perle        | IOLAN Console Servers | [perle_iolan.yaml](/backend/config/vendors/perle_iolan.yaml)                     |                                        |
| pfSense      |                       | [pfsense.yaml](/backend/config/vendors/pfsense.yaml)                             |                                        |
| SONiC        | Enterprise SONiC      | [sonic_enterprise.yaml](/backend/config/vendors/sonic_enterprise.yaml)           |                                        |
| TrueNAS      |                       | [truenas.yaml](/backend/config/vendors/truenas.yaml)                             | [TrueNAS](#truenas)                    |
| Ubiquiti     | UniFi                 | [ubiquiti_unifi.yaml](/backend/config/vendors/ubiquiti_unifi.yaml)               | [Ubiquiti](#ubiquiti)                  |
| Watchguard   | FirewareOS            | [watchguard_firewareos.yaml](/backend/config/vendors/watchguard_firewareos.yaml) |                                        |

---

## Cisco AireOS

**Cisco WLC Configuration**
Create a user with read-write privilege:

`mgmtuser add kiwissh **** read-write`

KiwiSSH needs read-write privilege in order to execute `config paging disable`.

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

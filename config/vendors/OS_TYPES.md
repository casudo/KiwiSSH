# Supported OS/Device Types

| Vendor   | OS/Device Type | YAML file                                                          | Notes                               |
| -------- | -------------- | ------------------------------------------------------------------ | ----------------------------------- |
| Cisco    | IOS            | [cisco_ios.yaml](/config/vendors/cisco_ios.yaml)                   |                                     |
| Fortinet | FortiGate      | [fortinet_fortigate.yaml](/config/vendors/fortinet_fortigate.yaml) | [FortiGate](#fortinet-device-types) |
| Fortinet | FortiOS        | [fortinet_fortios.yaml](/config/vendors/fortinet_fortios.yaml)     | [FortiOS](#fortinet-device-types)   |
| Ubiquiti | UniFi       | [ubiquiti_unifi.yaml](/config/vendors/ubiquiti_unifi.yaml)     | [Ubiquiti](#ubiquiti)               |

---

## Fortinet device types

There are two models for Fortinet devices:

- fortigate: for the FortiGate firewalls
- fortios: for VM-Based appliances (FortiManager, FortiADC, FortiAnalyzer...)

### Notes for both device types

#### Configuration changes / hiding passwords

FortiGate and FortiOS re-encrypt their passwords every time the configuration is shown. This results in a lot of apparent configuration changes on every pull.

To avoid this, enable the redaction feature inside the vendor YAML file (`redaction.enabled: true`). This will replace all passwords with a fixed string, so the configuration will only change when there are actual changes to the configuration.

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

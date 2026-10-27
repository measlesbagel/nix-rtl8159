# nix-rtl8159

The PHY firmware (`rtl_nic/rtl8159-1.fw`) that the in-kernel `r8152` driver
needs to bring a Realtek RTL8159 USB 10GbE adapter up at 10G, built from
Realtek's own driver source.

Without it the link tops out at 5G. The patch lives in the PHY's RAM, so
the adapter loses it with power and the driver reloads it on every plug-in,
skipping the load when the PHY already runs that version or newer.

## Use

```nix
# flake.nix
inputs.nix-rtl8159.url = "github:measlesbagel/nix-rtl8159/v2.22.1-1";
inputs.nix-rtl8159.inputs.nixpkgs.follows = "nixpkgs";

# the host's configuration
imports = [ inputs.nix-rtl8159.nixosModules.default ];
hardware.rtl8159.enable = true;
```

It needs kernel 7.2 or newer, the first whose `r8152` supports the RTL8159;
the module asserts it. The firmware alone is `packages.<system>.default`, or
`rtl8159-firmware` from `overlays.default`.

After a replug, `ethtool -i <iface>` shows the loaded file as
`firmware-version: rtl8159-1 v2.22.1 2026/06/03`, and `ethtool <iface>` shows
`Speed: 10000Mb/s` on a 10G link.

## How it is built

`r8152.c` is Realtek's out-of-tree r8152 driver, unmodified. Its
`rtl_ram_code_speed_up()` carries the RTL8159 patch as the `ram17[]` array
and its version as `code_ver`. `pack.py` writes both in the kernel's
firmware format: a sha256-checked header and one PHY speed-up block.
`verify.py` checks the result against the kernel's loading rules and
re-reads the patch from `r8152.c` on its own to compare.

Given rtlnic_fw's labels, `pack.py` reproduces
[rtlnic_fw](https://gitlab.com/koblitz-rtlnic/rtlnic_fw)'s `rtl8159-1.fw`
for driver 2.21.4 byte for byte.

## Updating

Realtek's download page sits behind a CAPTCHA, so updates are manual. The
`realtek-watch` workflow checks Realtek's listing weekly and opens an issue
when it lists a release newer than the newest tag. GitHub disables scheduled
workflows in a public repository after 60 days without activity, so if the
watcher goes quiet, re-enable it in the repository's Actions tab:

1. Replace `r8152.c` with the one from Realtek's newest r8152 tarball.
2. Set `version` in `package.nix` to that release; the build fails if they
   disagree.
3. Run `nix flake check`, then tag `v<release>-1`, bumping the suffix for
   packaging-only changes.

## License

GPL-2.0-only, like `r8152.c`.

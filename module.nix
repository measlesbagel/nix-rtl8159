{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.hardware.rtl8159;
in
{
  options.hardware.rtl8159 = {
    enable = lib.mkEnableOption "the PHY firmware the in-kernel r8152 driver needs to link an RTL8159 at 10G";
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./package.nix { };
      defaultText = lib.literalMD "the firmware packed from this flake's `r8152.c`";
      description = "Package providing `lib/firmware/rtl_nic/rtl8159-1.fw`.";
    };
  };

  config = lib.mkIf cfg.enable {
    hardware.firmware = [ cfg.package ];

    assertions = [
      {
        assertion = lib.versionAtLeast config.boot.kernelPackages.kernel.version "7.2";
        message = "hardware.rtl8159 needs kernel 7.2 or newer, the first whose r8152 drives the RTL8159";
      }
    ];
  };
}

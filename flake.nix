{
  description = "RTL8159 PHY firmware for the in-kernel r8152 driver, packed from Realtek's r8152.c";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;
      forAllSystems =
        f: lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: {
        default = pkgs.callPackage ./package.nix { };
      });

      overlays.default = final: _: {
        rtl8159-firmware = final.callPackage ./package.nix { };
      };

      nixosModules.default = ./module.nix;

      checks = forAllSystems (
        pkgs:
        let
          host = lib.nixosSystem {
            modules = [
              self.nixosModules.default
              {
                nixpkgs.hostPlatform = pkgs.stdenv.hostPlatform.system;
                boot.kernelPackages = pkgs.linuxPackages_latest;
                hardware.rtl8159.enable = true;
                fileSystems."/" = {
                  device = "none";
                  fsType = "tmpfs";
                };
                boot.loader.grub.enable = false;
                system.stateVersion = lib.trivial.release;
              }
            ];
          };
        in
        {
          firmware = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
          # Evaluating the toplevel runs the module's assertions without building a system.
          module = pkgs.runCommand "rtl8159-module-eval" { } ''
            echo ${builtins.unsafeDiscardStringContext host.config.system.build.toplevel.drvPath} > $out
          '';
        }
      );

      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}

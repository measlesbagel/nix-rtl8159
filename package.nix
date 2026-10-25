{
  lib,
  stdenvNoCC,
  python3,
}:
stdenvNoCC.mkDerivation {
  pname = "rtl8159-firmware";
  # The Realtek r8152 release ./r8152.c is; pack.py refuses any other.
  version = "2.21.4";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./r8152.c
      ./pack.py
      ./verify.py
    ];
  };

  nativeBuildInputs = [ python3 ];

  buildPhase = ''
    runHook preBuild
    python3 -I pack.py --driver-version "$version" r8152.c rtl8159-1.fw
    runHook postBuild
  '';

  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -I verify.py --source r8152.c rtl8159-1.fw
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    install -Dm444 rtl8159-1.fw -t "$out/lib/firmware/rtl_nic"
    runHook postInstall
  '';

  meta = {
    description = "RTL8159 PHY firmware for the in-kernel r8152 driver, packed from Realtek's r8152.c";
    homepage = "https://github.com/measlesbagel/nix-rtl8159";
    license = lib.licenses.gpl2Only;
    sourceProvenance = [ lib.sourceTypes.binaryFirmware ];
    platforms = lib.platforms.linux;
  };
}

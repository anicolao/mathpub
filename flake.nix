{
  description = "Reproducible, proof-aware mathematical worksheet publishing";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "aarch64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgsFor = system: import nixpkgs { inherit system; };
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          python = pkgs.python312;
          pythonPackages = pkgs.python312Packages;
          mathpubSource = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [
              ./README.md
              ./components
              ./mathpub.toml
              ./publications
              ./pyproject.toml
              ./src
              ./tests
            ];
          };
          guiSource = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [
              ./src-tauri
              ./src/mathpub/gui/static
            ];
          };
          tauriDriverSource = pkgs.fetchCrate {
            pname = "tauri-driver";
            version = "2.0.6";
            hash = "sha256-fTCkEs4NLBW0khaHL4jpVNkrbQg22YPsRMjfJNqnCWA=";
          };
          sage =
            if pkgs.stdenv.isDarwin then
              pkgs.sage.override
                {
                  inherit pkgs;
                  requireSageTests = false;
                  withDoc = false;
                }
            else
              pkgs.sage;
          tex = pkgs.texliveSmall.withPackages (ps: with ps; [
            cm-unicode
            doublestroke
            exam
            enumitem
            euler-math
            fancyhdr
            fontspec
            latexmk
            libertinus-fonts
            lualatex-math
            mathtools
            microtype
            mylatexformat
            siunitx
            standalone
            unicode-math
          ]);
          mathpub = pythonPackages.buildPythonApplication {
            pname = "mathpub";
            version = "0.1.0";
            pyproject = true;
            src = mathpubSource;
            build-system = [ pythonPackages.hatchling ];
            dependencies = [
              pythonPackages.jsonschema
              pythonPackages.numpy
              pythonPackages.pypdf
            ];
            nativeCheckInputs = [
              pkgs.git
              pkgs.poppler-utils
              pkgs.playwright-driver.browsers
              pythonPackages.pillow
              pythonPackages.playwright
              pythonPackages.pytestCheckHook
              sage
              tex
            ];
            preCheck = ''
              export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
              export PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
            '';
            nativeBuildInputs = [ pkgs.makeWrapper ];
            postInstall = ''
              wrapProgram $out/bin/mathpub \
                --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git sage tex pkgs.poppler-utils ]}
              makeWrapper $out/bin/mathpub $out/bin/mathpub-workspace \
                --add-flags "workspace"
            '';
            pythonImportsCheck = [ "mathpub" ];
            pytestFlags = [ "tests" ];
          };
          guiBuildInputs = pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.glib
            pkgs.gtk3
            pkgs.libayatana-appindicator
            pkgs.librsvg
            pkgs.libsoup_3
            pkgs.openssl
            pkgs.webkitgtk_4_1
          ];
          mathpub-gui-unwrapped = pkgs.rustPlatform.buildRustPackage {
            pname = "mathpub-gui";
            version = "0.1.0";
            src = guiSource;
            postUnpack = ''
              sourceRoot="$sourceRoot/src-tauri"
            '';
            cargoLock.lockFile = ./src-tauri/Cargo.lock;
            nativeBuildInputs = [
              pkgs.pkg-config
            ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
              pkgs.wrapGAppsHook3
            ];
            buildInputs = guiBuildInputs;
            postInstall = ''
              mv $out/bin/mathpub-gui $out/bin/MathPub
            '';
          };
          mathpub-gui = pkgs.symlinkJoin {
            name = "mathpub-gui-0.1.0";
            paths = [ mathpub-gui-unwrapped ];
            nativeBuildInputs = [ pkgs.makeWrapper ];
            postBuild = ''
              makeWrapper ${mathpub-gui-unwrapped}/bin/MathPub $out/bin/mathpub-gui \
                --set MATHPUB_GUI_BACKEND ${mathpub}/bin/mathpub
            '';
            passthru.unwrapped = mathpub-gui-unwrapped;
          };
          tauri-driver = pkgs.rustPlatform.buildRustPackage {
            pname = "tauri-driver";
            version = "2.0.6";
            src = tauriDriverSource;
            cargoLock.lockFile = "${tauriDriverSource}/Cargo.lock";
            doCheck = false;
            meta.platforms = pkgs.lib.platforms.linux;
          };
          guiTestPython = python.withPackages (ps: [
            ps.pillow
            ps.pytest
          ]);
          mathpub-gui-e2e =
            if pkgs.stdenv.isLinux then
              pkgs.writeShellApplication
                {
                  name = "mathpub-gui-e2e";
                  runtimeInputs = [
                    guiTestPython
                    pkgs.mesa
                    pkgs.webkitgtk_4_1
                    pkgs.xvfb-run
                    tauri-driver
                  ];
                  text = ''
                    export MATHPUB_GUI_BINARY=${mathpub-gui}/bin/MathPub
                    export MATHPUB_GUI_BACKEND=${mathpub}/bin/mathpub
                    export TAURI_DRIVER_BINARY=${tauri-driver}/bin/tauri-driver
                    export MATHPUB_GUI_NATIVE_SCREENSHOT="$PWD/build/e2e/tauri-driver.png"
                    export NO_AT_BRIDGE=1
                    export GDK_BACKEND=x11
                    export LIBGL_ALWAYS_SOFTWARE=1
                    export LIBGL_DRIVERS_PATH=${pkgs.mesa}/lib/dri
                    export __EGL_VENDOR_LIBRARY_FILENAMES=${pkgs.mesa}/share/glvnd/egl_vendor.d/50_mesa.json
                    export WEBKIT_DISABLE_DMABUF_RENDERER=1
                    ${mathpub}/bin/mathpub build publications/physics-practice.toml \
                      --seed 2026 --variant A --projection student --replace --json
                    exec xvfb-run -a pytest \
                      tests/e2e/002_gui_workspace/test_tauri_driver.py -v
                  '';
                }
            else
              pkgs.writeShellApplication {
                name = "mathpub-gui-e2e";
                text = ''
                  echo "Direct tauri-driver testing is supported on Linux and Windows only." >&2
                  exit 1
                '';
              };
        in
        {
          inherit mathpub mathpub-gui mathpub-gui-e2e;
          default = mathpub;
        } // pkgs.lib.optionalAttrs pkgs.stdenv.isLinux {
          inherit tauri-driver;
        });

      apps = forAllSystems (system: {
        mathpub = {
          type = "app";
          program = "${self.packages.${system}.mathpub}/bin/mathpub";
        };
        mathpub-workspace = {
          type = "app";
          program = "${self.packages.${system}.mathpub}/bin/mathpub-workspace";
        };
        mathpub-gui = {
          type = "app";
          program = "${self.packages.${system}.mathpub-gui}/bin/mathpub-gui";
        };
        mathpub-gui-e2e = {
          type = "app";
          program = "${self.packages.${system}.mathpub-gui-e2e}/bin/mathpub-gui-e2e";
        };
        default = self.apps.${system}.mathpub;
      });

      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          package = self.packages.${system}.mathpub;
          sage =
            if pkgs.stdenv.isDarwin then
              pkgs.sage.override
                {
                  inherit pkgs;
                  requireSageTests = false;
                  withDoc = false;
                }
            else
              pkgs.sage;
          tex = pkgs.texliveSmall.withPackages (ps: with ps; [
            cm-unicode
            doublestroke
            exam
            enumitem
            euler-math
            fancyhdr
            fontspec
            latexmk
            libertinus-fonts
            lualatex-math
            mathtools
            microtype
            mylatexformat
            siunitx
            standalone
            unicode-math
          ]);
        in
        {
          default = pkgs.mkShell {
            inputsFrom = [ package ];
            packages = [
              pkgs.gh
              pkgs.git
              pkgs.jq
              pkgs.cargo
              pkgs.cargo-tauri
              pkgs.ripgrep
              pkgs.rustc
              pkgs.rustfmt
              pkgs.python312Packages.pytest
              pkgs.python312Packages.ruff
              pkgs.poppler-utils
              pkgs.playwright-driver.browsers
              sage
              tex
            ];
            shellHook = ''
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
              export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
              export PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
            '';
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          package = self.packages.${system}.mathpub;
        in
        {
          package = package;
          gui = self.packages.${system}.mathpub-gui;
          formatting = pkgs.runCommand "mathpub-formatting"
            {
              nativeBuildInputs = [ pkgs.python312Packages.ruff ];
            } ''
            cp -R ${./.} source
            chmod -R u+w source
            cd source
            ruff format --check src tests
            ruff check src tests
            touch $out
          '';
        });

      formatter = forAllSystems (system: (pkgsFor system).nixpkgs-fmt);

      lib.mkPublicationProject =
        { src
        , projectName
        , publicationPaths ? [ ]
        }:
        {
          packages = self.packages;
          apps = self.apps;
          devShells = forAllSystems (system:
            let
              pkgs = pkgsFor system;
            in
            {
              default = pkgs.mkShell {
                packages = [
                  self.packages.${system}.mathpub
                  pkgs.gh
                  pkgs.git
                  pkgs.jq
                  pkgs.ripgrep
                ];
              };
            });
          formatter = self.formatter;
          checks = forAllSystems (system:
            let
              pkgs = pkgsFor system;
              mathpub = self.packages.${system}.mathpub;
              publicationCommands = pkgs.lib.concatStringsSep "\n"
                (pkgs.lib.imap0
                  (index: publicationPath: ''
                    ${mathpub}/bin/mathpub check publication \
                      ${pkgs.lib.escapeShellArg publicationPath} --json \
                      > "$out/publication-${toString index}.json"
                  '')
                  publicationPaths);
            in
            {
              content = pkgs.runCommand "${projectName}-mathpub-content" { } ''
                cp -R ${src} source
                chmod -R u+w source
                cd source
                export HOME="$TMPDIR"
                mkdir -p "$out"
                ${mathpub}/bin/mathpub check project --json > "$out/project.json"
                ${publicationCommands}
              '';
            });
        };
    };
}

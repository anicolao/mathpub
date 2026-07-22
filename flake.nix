{
  description = "Reproducible, proof-aware mathematical worksheet publishing";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgsFor = system: import nixpkgs {
        inherit system;
        overlays = [
          (_final: prev: if system == "aarch64-darwin" || system == "x86_64-darwin" then {
            singular = prev.singular.overrideAttrs (_old: {
              doCheck = false;
            });
          } else { })
        ];
      };
    in {
      packages = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          python = pkgs.python312;
          pythonPackages = pkgs.python312Packages;
          sage = pkgs.sage.override {
            inherit pkgs;
            requireSageTests = false;
            withDoc = false;
          };
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
            siunitx
            standalone
            unicode-math
          ]);
          mathpub = pythonPackages.buildPythonApplication {
            pname = "mathpub";
            version = "0.1.0";
            pyproject = true;
            src = ./.;
            build-system = [ pythonPackages.hatchling ];
            dependencies = [
              pythonPackages.jsonschema
              pythonPackages.numpy
              pythonPackages.pypdf
              pythonPackages.pillow
              pythonPackages.playwright
            ];
            nativeCheckInputs = [
              pkgs.git
              pkgs.poppler-utils
              pkgs.playwright-driver.browsers
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
        in {
          inherit mathpub;
          default = mathpub;
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
          program = "${self.packages.${system}.mathpub}/bin/mathpub-workspace";
        };
        default = self.apps.${system}.mathpub;
      });

      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          package = self.packages.${system}.mathpub;
          sage = pkgs.sage.override {
            inherit pkgs;
            requireSageTests = false;
            withDoc = false;
          };
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
            siunitx
            standalone
            unicode-math
          ]);
        in {
          default = pkgs.mkShell {
            inputsFrom = [ package ];
            packages = [
              pkgs.gh
              pkgs.git
              pkgs.jq
              pkgs.ripgrep
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
        in {
          package = package;
          formatting = pkgs.runCommand "mathpub-formatting" {
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
            in {
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
            in {
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

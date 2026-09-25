#!/usr/bin/env python3
"""
temp.py -- run from:
    C:\\Users\\user\\Home\\.obsidian\\obsidian-sequential-nav\\temp.py

Rewrites the plugin source, builds, and installs into the vault.
Includes default hotkeys: Alt+[ (previous), Alt+] (next).

Usage:
    python temp.py            # write + build + install
    python temp.py --source   # write source files only
    python temp.py --build    # build only (skip source rewrite)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ID = "sequential-note-nav"
PLUGIN_NAME = "Sequential Note Navigator"


def J(*lines):
    return "\n".join(lines) + "\n"


MANIFEST = json.dumps({
    "id": PLUGIN_ID,
    "name": PLUGIN_NAME,
    "version": "1.0.0",
    "minAppVersion": "1.0.0",
    "description": "Jump to the previous or next note by creation or modification time.",
    "author": "You",
    "isDesktopOnly": False,
}, indent=2) + "\n"

PACKAGE_JSON = json.dumps({
    "name": "obsidian-sequential-nav",
    "version": "1.0.0",
    "scripts": {
        "dev": "node esbuild.config.mjs",
        "build": "tsc -noEmit -skipLibCheck && node esbuild.config.mjs production",
    },
    "devDependencies": {
        "obsidian": "latest",
        "typescript": "^5.0.0",
        "esbuild": "^0.19.0",
        "@types/node": "^20.0.0",
    },
}, indent=2) + "\n"

TSCONFIG = json.dumps({
    "compilerOptions": {
        "target": "ES2018",
        "module": "ESNext",
        "moduleResolution": "node",
        "strict": True,
        "esModuleInterop": True,
        "skipLibCheck": True,
        "lib": ["DOM", "ES2018"],
    },
    "include": ["main.ts"],
}, indent=2) + "\n"

VERSIONS_JSON = json.dumps({"1.0.0": "1.0.0"}, indent=2) + "\n"

ESBUILD_CONFIG = J(
    'import esbuild from "esbuild";',
    'import process from "process";',
    "",
    'const prod = process.argv[2] === "production";',
    "",
    "esbuild.build({",
    '  entryPoints: ["main.ts"],',
    "  bundle: true,",
    '  external: ["obsidian"],',
    '  format: "cjs",',
    '  target: "es2018",',
    '  sourcemap: prod ? false : "inline",',
    '  outfile: "main.js",',
    "}).catch(() => process.exit(1));",
)

MAIN_TS = J(
    "import { App, Plugin, PluginSettingTab, Setting, TFile, Notice } from 'obsidian';",
    "",
    "interface SeqNavSettings {",
    "  sortBy: 'ctime' | 'mtime';",
    "  scope: 'vault' | 'folder';",
    "  wrapAround: boolean;",
    "}",
    "",
    "const DEFAULT_SETTINGS: SeqNavSettings = {",
    "  sortBy: 'mtime',",
    "  scope: 'vault',",
    "  wrapAround: false,",
    "};",
    "",
    "const CMD_PREV = 'open-previous-note';",
    "const CMD_NEXT = 'open-next-note';",
    "",
    "// Default hotkey bindings we want to seed into Obsidian.",
    "// Modifiers: Mod=Ctrl (Win/Linux) or Cmd (macOS); Alt is Alt everywhere.",
    "// The bracket keys: '[' and ']'.",
    "const DEFAULT_HOTKEYS: Record<string, { modifiers: string[]; key: string }[]> = {",
    "  [CMD_PREV]: [{ modifiers: ['Alt'], key: '[' }],",
    "  [CMD_NEXT]: [{ modifiers: ['Alt'], key: ']' }],",
    "};",
    "",
    "export default class SeqNavPlugin extends Plugin {",
    "  settings!: SeqNavSettings;",
    "",
    "  async onload() {",
    "    await this.loadSettings();",
    "",
    "    this.addCommand({",
    "      id: CMD_PREV,",
    "      name: 'Open previous note',",
    "      callback: () => this.navigate(-1),",
    "    });",
    "",
    "    this.addCommand({",
    "      id: CMD_NEXT,",
    "      name: 'Open next note',",
    "      callback: () => this.navigate(1),",
    "    });",
    "",
    "    this.addSettingTab(new SeqNavSettingTab(this.app, this));",
    "",
    "    // Seed default hotkeys if the user hasn't set any yet.",
    "    this.seedDefaultHotkeys();",
    "  }",
    "",
    "  /**",
    "   * Try to write default hotkeys into Obsidian's hotkey config.",
    "   * Uses undocumented internals; falls back to a notice if unavailable.",
    "   * Existing user bindings are never overwritten.",
    "   */",
    "  seedDefaultHotkeys() {",
    "    const app = this.app as any;",
    "    const hm = app.hotkeyManager;",
    "    if (!hm || !hm.customKeys) {",
    "      new Notice('Sequential Note Navigator: bind Alt+[ and Alt+] in Settings -> Hotkeys.');",
    "      return;",
    "    }",
    "",
    "    let changed = false;",
    "    for (const [cmdId, bindings] of Object.entries(DEFAULT_HOTKEYS)) {",
    "      const fullId = `${this.manifest.id}:${cmdId}`;",
    "      const existing = hm.customKeys[fullId];",
    "      if (existing && existing.length > 0) continue; // respect user's choice",
    "      hm.customKeys[fullId] = bindings.map((b) => ({",
    "        modifiers: b.modifiers,",
    "        key: b.key,",
    "      }));",
    "      changed = true;",
    "    }",
    "",
    "    if (changed && typeof hm.save === 'function') {",
    "      try {",
    "        hm.save();",
    "      } catch (e) {",
    "        console.warn('SeqNav: could not persist hotkeys', e);",
    "      }",
    "    }",
    "  }",
    "",
    "  async navigate(direction: 1 | -1) {",
    "    const active = this.app.workspace.getActiveFile();",
    "    if (!active) {",
    "      new Notice('No active note.');",
    "      return;",
    "    }",
    "",
    "    const ordered = this.getOrderedNotes(active);",
    "    const idx = ordered.findIndex((f) => f.path === active.path);",
    "    if (idx === -1) return;",
    "",
    "    let target = idx + direction;",
    "",
    "    if (target < 0 || target >= ordered.length) {",
    "      if (!this.settings.wrapAround) {",
    "        new Notice(direction === 1 ? 'Already at last note.' : 'Already at first note.');",
    "        return;",
    "      }",
    "      target = (target + ordered.length) % ordered.length;",
    "    }",
    "",
    "    await this.app.workspace.getLeaf(false).openFile(ordered[target]);",
    "  }",
    "",
    "  getOrderedNotes(active: TFile): TFile[] {",
    "    const all = this.app.vault.getMarkdownFiles();",
    "",
    "    const inScope = this.settings.scope === 'folder'",
    "      ? all.filter((f) => f.parent?.path === active.parent?.path)",
    "      : all;",
    "",
    "    const sortBy = this.settings.sortBy;",
    "",
    "    return inScope.sort((a, b) => {",
    "      const av = sortBy === 'ctime' ? a.stat.ctime : a.stat.mtime;",
    "      const bv = sortBy === 'ctime' ? b.stat.ctime : b.stat.mtime;",
    "      if (av !== bv) return av - bv;",
    "      return a.path.localeCompare(b.path);",
    "    });",
    "  }",
    "",
    "  async loadSettings() {",
    "    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());",
    "  }",
    "",
    "  async saveSettings() {",
    "    await this.saveData(this.settings);",
    "  }",
    "}",
    "",
    "class SeqNavSettingTab extends PluginSettingTab {",
    "  plugin: SeqNavPlugin;",
    "",
    "  constructor(app: App, plugin: SeqNavPlugin) {",
    "    super(app, plugin);",
    "    this.plugin = plugin;",
    "  }",
    "",
    "  display() {",
    "    const { containerEl } = this;",
    "    containerEl.empty();",
    "",
    "    new Setting(containerEl)",
    "      .setName('Sort by')",
    "      .setDesc('Which timestamp to use for ordering notes.')",
    "      .addDropdown((dd) =>",
    "        dd",
    "          .addOption('mtime', 'Modification time')",
    "          .addOption('ctime', 'Creation time')",
    "          .setValue(this.plugin.settings.sortBy)",
    "          .onChange(async (v) => {",
    "            this.plugin.settings.sortBy = v as 'ctime' | 'mtime';",
    "            await this.plugin.saveSettings();",
    "          })",
    "      );",
    "",
    "    new Setting(containerEl)",
    "      .setName('Scope')",
    "      .setDesc('Navigate across the whole vault or only within the current folder.')",
    "      .addDropdown((dd) =>",
    "        dd",
    "          .addOption('vault', 'Whole vault')",
    "          .addOption('folder', 'Current folder only')",
    "          .setValue(this.plugin.settings.scope)",
    "          .onChange(async (v) => {",
    "            this.plugin.settings.scope = v as 'vault' | 'folder';",
    "            await this.plugin.saveSettings();",
    "          })",
    "      );",
    "",
    "    new Setting(containerEl)",
    "      .setName('Wrap around')",
    "      .setDesc('Navigating past the last note goes to the first, and vice versa.')",
    "      .addToggle((t) =>",
    "        t",
    "          .setValue(this.plugin.settings.wrapAround)",
    "          .onChange(async (v) => {",
    "            this.plugin.settings.wrapAround = v;",
    "            await this.plugin.saveSettings();",
    "          })",
    "      );",
    "  }",
    "}",
)

README_MD = J(
    "# Sequential Note Navigator",
    "",
    "Jump to the previous or next note by creation or modification time.",
    "",
    "## Commands and default hotkeys",
    "",
    "- `Open previous note` — **Alt + [**",
    "- `Open next note` — **Alt + ]**",
    "",
    "If the defaults were not applied automatically, bind them under",
    "**Settings -> Hotkeys** (search for `Sequential`).",
    "",
    "## Settings",
    "",
    "| Setting     | Options                           |",
    "|-------------|-----------------------------------|",
    "| Sort by     | Modification time / Creation time |",
    "| Scope       | Whole vault / Current folder only |",
    "| Wrap around | On / Off                          |",
)

GITIGNORE = J(
    "node_modules/",
    "main.js",
    "*.log",
    ".DS_Store",
)

FILES = {
    "manifest.json": MANIFEST,
    "package.json": PACKAGE_JSON,
    "tsconfig.json": TSCONFIG,
    "versions.json": VERSIONS_JSON,
    "esbuild.config.mjs": ESBUILD_CONFIG,
    "main.ts": MAIN_TS,
    "README.md": README_MD,
    ".gitignore": GITIGNORE,
}


def run(cmd, cwd):
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True, shell=(os.name == "nt"))


def write_source(folder: Path):
    for name, content in FILES.items():
        (folder / name).write_text(content, encoding="utf-8", newline="\n")
        print(f"  wrote {name}")


def build(folder: Path):
    if shutil.which("npm") is None:
        print("!! npm not found on PATH.", file=sys.stderr)
        sys.exit(1)
    if not (folder / "node_modules").exists():
        run(["npm", "install"], cwd=folder)
    run(["npm", "run", "build"], cwd=folder)
    if not (folder / "main.js").exists():
        print("!! main.js was not produced; build failed.", file=sys.stderr)
        sys.exit(1)


def find_vault(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(20):
        if (cur / ".obsidian").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    print("!! Could not find a vault (no .obsidian folder above this one).",
          file=sys.stderr)
    sys.exit(1)


def install(folder: Path, vault: Path):
    dest = vault / ".obsidian" / "plugins" / PLUGIN_ID
    dest.mkdir(parents=True, exist_ok=True)
    for f in ("manifest.json", "main.js"):
        shutil.copy2(folder / f, dest / f)
        print(f"  copied {f} -> {dest / f}")
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="store_true",
                    help="Only write source files; do not build.")
    ap.add_argument("--build", action="store_true",
                    help="Only build and install; do not rewrite source files.")
    args = ap.parse_args()

    folder = Path(__file__).resolve().parent
    vault = find_vault(folder)
    print(f"Source folder : {folder}")
    print(f"Vault         : {vault}")
    print()

    if not args.build:
        print("[1/3] Writing source files")
        write_source(folder)
        print()

    if args.source:
        print("Done (--source). No build performed.")
        return

    print("[2/3] Building")
    build(folder)
    print()

    print("[3/3] Installing into vault")
    dest = install(folder, vault)
    print()
    print(f"[OK] Installed to {dest}")
    print()
    print("Next in Obsidian:")
    print("  1. Ctrl+R to reload.")
    print("  2. If the plugin was already enabled, toggle it off then on so")
    print("     the new default hotkeys get seeded.")
    print("  3. Alt+[ and Alt+] should now navigate notes.")
    print("     If not, bind them manually in Settings -> Hotkeys.")


if __name__ == "__main__":
    main()
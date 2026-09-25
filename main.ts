import { App, Plugin, PluginSettingTab, Setting, TFile, Notice } from 'obsidian';

interface SeqNavSettings {
  sortBy: 'ctime' | 'mtime';
  scope: 'vault' | 'folder';
  wrapAround: boolean;
}

const DEFAULT_SETTINGS: SeqNavSettings = {
  sortBy: 'mtime',
  scope: 'vault',
  wrapAround: false,
};

const CMD_PREV = 'open-previous-note';
const CMD_NEXT = 'open-next-note';

// Default hotkey bindings we want to seed into Obsidian.
// Modifiers: Mod=Ctrl (Win/Linux) or Cmd (macOS); Alt is Alt everywhere.
// The bracket keys: '[' and ']'.
const DEFAULT_HOTKEYS: Record<string, { modifiers: string[]; key: string }[]> = {
  [CMD_PREV]: [{ modifiers: ['Alt'], key: '[' }],
  [CMD_NEXT]: [{ modifiers: ['Alt'], key: ']' }],
};

export default class SeqNavPlugin extends Plugin {
  settings!: SeqNavSettings;

  async onload() {
    await this.loadSettings();

    this.addCommand({
      id: CMD_PREV,
      name: 'Open previous note',
      callback: () => this.navigate(-1),
    });

    this.addCommand({
      id: CMD_NEXT,
      name: 'Open next note',
      callback: () => this.navigate(1),
    });

    this.addSettingTab(new SeqNavSettingTab(this.app, this));

    // Seed default hotkeys if the user hasn't set any yet.
    this.seedDefaultHotkeys();
  }

  /**
   * Try to write default hotkeys into Obsidian's hotkey config.
   * Uses undocumented internals; falls back to a notice if unavailable.
   * Existing user bindings are never overwritten.
   */
  seedDefaultHotkeys() {
    const app = this.app as any;
    const hm = app.hotkeyManager;
    if (!hm || !hm.customKeys) {
      new Notice('Sequential Note Navigator: bind Alt+[ and Alt+] in Settings -> Hotkeys.');
      return;
    }

    let changed = false;
    for (const [cmdId, bindings] of Object.entries(DEFAULT_HOTKEYS)) {
      const fullId = `${this.manifest.id}:${cmdId}`;
      const existing = hm.customKeys[fullId];
      if (existing && existing.length > 0) continue; // respect user's choice
      hm.customKeys[fullId] = bindings.map((b) => ({
        modifiers: b.modifiers,
        key: b.key,
      }));
      changed = true;
    }

    if (changed && typeof hm.save === 'function') {
      try {
        hm.save();
      } catch (e) {
        console.warn('SeqNav: could not persist hotkeys', e);
      }
    }
  }

  async navigate(direction: 1 | -1) {
    const active = this.app.workspace.getActiveFile();
    if (!active) {
      new Notice('No active note.');
      return;
    }

    const ordered = this.getOrderedNotes(active);
    const idx = ordered.findIndex((f) => f.path === active.path);
    if (idx === -1) return;

    let target = idx + direction;

    if (target < 0 || target >= ordered.length) {
      if (!this.settings.wrapAround) {
        new Notice(direction === 1 ? 'Already at last note.' : 'Already at first note.');
        return;
      }
      target = (target + ordered.length) % ordered.length;
    }

    await this.app.workspace.getLeaf(false).openFile(ordered[target]);
  }

  getOrderedNotes(active: TFile): TFile[] {
    const all = this.app.vault.getMarkdownFiles();

    const inScope = this.settings.scope === 'folder'
      ? all.filter((f) => f.parent?.path === active.parent?.path)
      : all;

    const sortBy = this.settings.sortBy;

    return inScope.sort((a, b) => {
      const av = sortBy === 'ctime' ? a.stat.ctime : a.stat.mtime;
      const bv = sortBy === 'ctime' ? b.stat.ctime : b.stat.mtime;
      if (av !== bv) return av - bv;
      return a.path.localeCompare(b.path);
    });
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }
}

class SeqNavSettingTab extends PluginSettingTab {
  plugin: SeqNavPlugin;

  constructor(app: App, plugin: SeqNavPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName('Sort by')
      .setDesc('Which timestamp to use for ordering notes.')
      .addDropdown((dd) =>
        dd
          .addOption('mtime', 'Modification time')
          .addOption('ctime', 'Creation time')
          .setValue(this.plugin.settings.sortBy)
          .onChange(async (v) => {
            this.plugin.settings.sortBy = v as 'ctime' | 'mtime';
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('Scope')
      .setDesc('Navigate across the whole vault or only within the current folder.')
      .addDropdown((dd) =>
        dd
          .addOption('vault', 'Whole vault')
          .addOption('folder', 'Current folder only')
          .setValue(this.plugin.settings.scope)
          .onChange(async (v) => {
            this.plugin.settings.scope = v as 'vault' | 'folder';
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('Wrap around')
      .setDesc('Navigating past the last note goes to the first, and vice versa.')
      .addToggle((t) =>
        t
          .setValue(this.plugin.settings.wrapAround)
          .onChange(async (v) => {
            this.plugin.settings.wrapAround = v;
            await this.plugin.saveSettings();
          })
      );
  }
}

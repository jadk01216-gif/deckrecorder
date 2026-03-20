# encoding: utf-8
import zipfile
import json
import os

# --- v4.0 終極修復與新功能 ---
# 1. 修復存檔失敗：在 build_addon 中強制寫入 config.json，滿足 Anki 的官方 API 需求。
# 2. 新增功能：可設定新牌組預設要放入哪個「父牌組 (Target Deck)」底下。
# 3. 邏輯優化：修復若手動建立子牌組時，無法正確辨識為新牌組的 Bug。

ADDON_CODE = """
import time
from aqt import mw
from aqt.qt import *
from aqt.utils import tooltip
from aqt import gui_hooks

# --- Constants ---
CHAR_0 = '\\u200b'
CHAR_1 = '\\u200c'
CONF_KEY_LANG = "reorder_lang" 
CONF_KEY_POS = "new_deck_pos" 
CONF_KEY_AUTO = "auto_reorder" 
CONF_KEY_TARGET_DECK = "auto_target_deck"

_is_reordering = False

# --- I18N ---
I18N = {
    "zh-TW": {
        "menu_name": "⇅ 牌組重排",
        "move_top": "⏫ 移至頂部",
        "move_up": "🔼 上移",
        "move_down": "🔽 下移",
        "move_btm": "⏬ 移至底部",
        "adv_mgr": "🛠️ 進階管理器...",
        "save": "✅ 儲存並套用",
        "title": "進階排序管理器 (v4.0)",
        "success": "設定已存檔並套用",
        "settings_group": "自動化與介面設定",
        "lang_label": "介面語言 (Language):",
        "new_deck_label": "新牌組排序位置:",
        "target_deck_label": "預設放入的父牌組:",
        "target_root": "< 最上層 (無) >",
        "pos_top": "最上面",
        "pos_bottom": "最下面",
        "auto_reorder_label": "發現新牌組時自動處理並重排"
    },
    "en": {
        "menu_name": "⇅ Deck Reorder",
        "move_top": "⏫ Move to Top",
        "move_up": "🔼 Move Up",
        "move_down": "🔽 Move Down",
        "move_btm": "⏬ Move to Bottom",
        "adv_mgr": "🛠️ Advanced Manager...",
        "save": "✅ Save and Apply",
        "title": "Advanced Deck Manager (v4.0)",
        "success": "Settings saved and applied",
        "settings_group": "Automation & UI Settings",
        "lang_label": "Interface Language:",
        "new_deck_label": "New Deck Position:",
        "target_deck_label": "Default Parent Deck:",
        "target_root": "< Root (None) >",
        "pos_top": "Top",
        "pos_bottom": "Bottom",
        "auto_reorder_label": "Auto-process & reorder new decks"
    }
}

def get_current_config():
    conf = mw.addonManager.getConfig(__name__)
    if not isinstance(conf, dict):
        conf = {}
    if CONF_KEY_LANG not in conf: conf[CONF_KEY_LANG] = "en"
    if CONF_KEY_POS not in conf: conf[CONF_KEY_POS] = "top"
    if CONF_KEY_AUTO not in conf: conf[CONF_KEY_AUTO] = True
    if CONF_KEY_TARGET_DECK not in conf: conf[CONF_KEY_TARGET_DECK] = ""
    return conf

def get_msg(key, lang_override=None):
    lang = lang_override if lang_override else get_current_config().get(CONF_KEY_LANG, "en")
    return I18N.get(lang, I18N["en"]).get(key, key)

def clean_name(name: str) -> str:
    return name.replace(CHAR_0, '').replace(CHAR_1, '')

def is_unsorted(name: str) -> bool:
    # 檢查最後一個層級是否有零寬字元 (確保子牌組也能正確判定為新牌組)
    final_part = name.split('::')[-1]
    return CHAR_0 not in final_part and CHAR_1 not in final_part

def apply_order_ultimate(ordered_ids):
    global _is_reordering
    if not ordered_ids or _is_reordering: return
    _is_reordering = True
    try:
        mw.checkpoint("Deck Reorder")
        mw.col.modSchema(check=False)
        all_decks = list(mw.col.decks.all_names_and_ids())
        id_to_base = {d.id: clean_name(d.name) for d in all_decks if d.id != 1}
        clean_path_to_id = {clean_name(d.name): d.id for d in all_decks if d.id != 1}
        
        temp_root = f"__REORDER_{int(time.time())}__"
        for d in all_decks:
            if d.id == 1: continue
            deck = mw.col.decks.get(d.id)
            if deck: mw.col.decks.rename(deck, f"{temp_root}_{d.id}")
        mw.col.decks.save()

        id_to_new_single_label = {}
        for counter, did in enumerate(ordered_ids):
            if did not in id_to_base: continue
            base = id_to_base[did]
            single_name = base.split('::')[-1]
            prefix = format(counter, '016b').replace('0', CHAR_0).replace('1', CHAR_1)
            id_to_new_single_label[did] = prefix + single_name

        tasks = []
        for did in ordered_ids:
            if did not in id_to_base: continue
            parts = id_to_base[did].split('::')
            new_path_parts = []
            curr = ""
            for p in parts:
                curr = (curr + "::" + p) if curr else p
                layer_id = clean_path_to_id.get(curr)
                new_path_parts.append(id_to_new_single_label.get(layer_id, p))
            tasks.append((did, '::'.join(new_path_parts)))

        tasks.sort(key=lambda x: x[1].count('::'))
        for did, final_name in tasks:
            tmp = f"{temp_root}_{did}"
            did_now = mw.col.decks.id_for_name(tmp)
            if did_now: mw.col.decks.rename(mw.col.decks.get(did_now), final_name)

        mw.col.decks.save()
        mw.reset()
        if mw.deckBrowser: mw.deckBrowser.refresh()
    finally:
        _is_reordering = False

def check_auto(deck_browser=None):
    if _is_reordering: return
    conf = get_current_config()
    if not conf.get(CONF_KEY_AUTO, True): return
    
    all_d = [d for d in mw.col.decks.all_names_and_ids() if d.id != 1]
    new_d = [d for d in all_d if is_unsorted(d.name)]
    if not new_d: return
    
    # 處理「預設放入的父牌組」
    target_deck_clean = conf.get(CONF_KEY_TARGET_DECK, "")
    moved_any = False
    if target_deck_clean:
        clean_names = {clean_name(d.name): d.name for d in all_d}
        if target_deck_clean in clean_names:
            target_raw = clean_names[target_deck_clean]
            for d in new_d:
                base_clean = clean_name(d.name)
                # 只有當牌組是建在最上層時(沒有 '::')，才把它移進目標父牌組
                if '::' not in base_clean:
                    deck_obj = mw.col.decks.get(d.id)
                    new_full = f"{target_raw}::{base_clean}"
                    mw.col.decks.rename(deck_obj, new_full)
                    moved_any = True
            
            if moved_any:
                mw.col.decks.save()
                # 重新獲取牌組資料，因為名字已經變更了
                all_d = [d for d in mw.col.decks.all_names_and_ids() if d.id != 1]
                new_d = [d for d in all_d if is_unsorted(d.name)]

    ids = [d.id for d in sorted(all_d, key=lambda d: d.name)]
    n_ids = [d.id for d in new_d]
    for nid in n_ids: 
        if nid in ids: ids.remove(nid)
    
    ids = (n_ids + ids) if conf.get(CONF_KEY_POS, "top") == "top" else (ids + n_ids)
    apply_order_ultimate(ids)

def quick_move(did, op):
    all_d = sorted([d for d in mw.col.decks.all_names_and_ids() if d.id != 1], key=lambda d: d.name)
    ids = [d.id for d in all_d]
    if did not in ids: return
    idx = ids.index(did)
    if op == "up" and idx > 0: ids[idx], ids[idx-1] = ids[idx-1], ids[idx]
    elif op == "down" and idx < len(ids)-1: ids[idx], ids[idx+1] = ids[idx+1], ids[idx]
    elif op == "top": ids.remove(did); ids.insert(0, did)
    elif op == "btm": ids.remove(did); ids.append(did)
    apply_order_ultimate(ids)
    tooltip(get_msg("success"))

class DeckManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conf = get_current_config()
        self.setFixedWidth(460)
        self.setFixedHeight(580) # 稍微加高以容納新選項
        self.setup_ui()
        self.update_dialog_texts()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)

        self.settings_group = QGroupBox()
        s_lay = QVBoxLayout()
        
        # 1. 語言設定
        lang_row = QHBoxLayout()
        self.lang_label = QLabel()
        lang_row.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("繁體中文", "zh-TW")
        idx_lang = self.lang_combo.findData(self.conf.get(CONF_KEY_LANG, "en"))
        self.lang_combo.setCurrentIndex(idx_lang if idx_lang != -1 else 0)
        self.lang_combo.currentIndexChanged.connect(self.update_dialog_texts)
        lang_row.addWidget(self.lang_combo)
        s_lay.addLayout(lang_row)

        # 2. 自動重排勾選框
        self.auto_cb = QCheckBox()
        self.auto_cb.setChecked(self.conf.get(CONF_KEY_AUTO, True))
        s_lay.addWidget(self.auto_cb)
        
        # 3. 預設父牌組選擇
        target_row = QHBoxLayout()
        self.target_deck_label = QLabel()
        target_row.addWidget(self.target_deck_label)
        self.target_combo = QComboBox()
        
        self.target_combo.addItem(get_msg("target_root", self.lang_combo.currentData()), "")
        decks_clean = sorted([clean_name(d.name) for d in mw.col.decks.all_names_and_ids() if d.id != 1])
        for d_name in decks_clean:
            self.target_combo.addItem(d_name, d_name)
            
        idx_target = self.target_combo.findData(self.conf.get(CONF_KEY_TARGET_DECK, ""))
        self.target_combo.setCurrentIndex(idx_target if idx_target != -1 else 0)
        target_row.addWidget(self.target_combo)
        s_lay.addLayout(target_row)

        # 4. 新牌組頂部/底部選擇
        row = QHBoxLayout()
        self.new_deck_label = QLabel()
        row.addWidget(self.new_deck_label)
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("", "top")
        self.pos_combo.addItem("", "bottom")
        idx_pos = self.pos_combo.findData(self.conf.get(CONF_KEY_POS, "top"))
        self.pos_combo.setCurrentIndex(idx_pos if idx_pos != -1 else 0)
        row.addWidget(self.pos_combo)
        s_lay.addLayout(row)
        
        self.settings_group.setLayout(s_lay)
        self.layout.addWidget(self.settings_group)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.layout.addWidget(self.tree)
        
        self.btn_save = QPushButton()
        self.btn_save.setFixedHeight(50)
        self.btn_save.setStyleSheet("font-weight: bold; background-color: #2ecc71; color: white; border-radius: 6px;")
        self.btn_save.clicked.connect(self.save)
        self.layout.addWidget(self.btn_save)
        
        self.load_tree()

    def update_dialog_texts(self):
        lang = self.lang_combo.currentData()
        self.setWindowTitle(get_msg("title", lang))
        self.settings_group.setTitle(get_msg("settings_group", lang))
        self.lang_label.setText(get_msg("lang_label", lang))
        self.auto_cb.setText(get_msg("auto_reorder_label", lang))
        self.target_deck_label.setText(get_msg("target_deck_label", lang))
        self.target_combo.setItemText(0, get_msg("target_root", lang))
        self.new_deck_label.setText(get_msg("new_deck_label", lang))
        self.pos_combo.setItemText(0, get_msg("pos_top", lang))
        self.pos_combo.setItemText(1, get_msg("pos_bottom", lang))
        self.btn_save.setText(get_msg("save", lang))

    def load_tree(self):
        self.tree.clear()
        decks = sorted([d for d in mw.col.decks.all_names_and_ids() if d.id != 1], key=lambda d: d.name)
        nodes = {}
        for d in decks:
            pts = clean_name(d.name).split('::')
            parent = self.tree.invisibleRootItem()
            if len(pts) > 1:
                pk = '::'.join(pts[:-1])
                if pk in nodes: parent = nodes[pk]
            item = QTreeWidgetItem(parent)
            item.setText(0, pts[-1])
            item.setData(0, Qt.ItemDataRole.UserRole, d.id)
            item.setExpanded(True)
            nodes['::'.join(pts)] = item

    def save(self):
        final_lang = self.lang_combo.currentData()
        new_conf = {
            CONF_KEY_LANG: final_lang,
            CONF_KEY_AUTO: self.auto_cb.isChecked(), 
            CONF_KEY_TARGET_DECK: self.target_combo.currentData(),
            CONF_KEY_POS: self.pos_combo.currentData()
        }
        
        # 寫入設定到 meta.json
        mw.addonManager.writeConfig(__name__, new_conf)
        
        for action in mw.form.menuTools.actions():
            if action.property("id") == "reorder_mgr_action":
                action.setText(get_msg("adv_mgr", final_lang))
                
        ids = []
        def traverse(p):
            for i in range(p.childCount()):
                c = p.child(i)
                ids.append(c.data(0, Qt.ItemDataRole.UserRole))
                traverse(c)
        traverse(self.tree.invisibleRootItem())
        apply_order_ultimate(ids)
        
        tooltip(get_msg("success", final_lang))
        self.accept()

def on_deck_menu(menu, did):
    if did == 1: return
    sub = menu.addMenu(get_msg("menu_name"))
    sub.addAction(get_msg("move_top")).triggered.connect(lambda: quick_move(did, "top"))
    sub.addAction(get_msg("move_up")).triggered.connect(lambda: quick_move(did, "up"))
    sub.addAction(get_msg("move_down")).triggered.connect(lambda: quick_move(did, "down"))
    sub.addAction(get_msg("move_btm")).triggered.connect(lambda: quick_move(did, "btm"))
    sub.addSeparator()
    sub.addAction(get_msg("adv_mgr")).triggered.connect(lambda: DeckManagerDialog(mw).exec())

def init():
    gui_hooks.deck_browser_will_show_options_menu.append(on_deck_menu)
    gui_hooks.deck_browser_did_render.append(check_auto)
    
    action = QAction(get_msg("adv_mgr"), mw)
    action.setProperty("id", "reorder_mgr_action")
    action.triggered.connect(lambda: DeckManagerDialog(mw).exec())
    mw.form.menuTools.addAction(action)

gui_hooks.main_window_did_init.append(init)
"""

MANIFEST = {
    "package": "UltimateDeckReorderPlus",
    "name": "Ultimate Deck Reorder (v4.0)",
    "mod": 1710850008
}

DEFAULT_CONFIG = {
    "reorder_lang": "en",
    "new_deck_pos": "top",
    "auto_reorder": True,
    "auto_target_deck": ""
}

def build_addon():
    filename = 'UltimateDeckReorderPlus.ankiaddon'
    with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('__init__.py', ADDON_CODE.strip())
        zf.writestr('manifest.json', json.dumps(MANIFEST, indent=4, ensure_ascii=False))
        # 【最關鍵的修復】必須在插件內打包 config.json，否則 Anki 不會啟動 Config 寫入機制！
        zf.writestr('config.json', json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False))
        
    print(f"Build Successful: {os.path.abspath(filename)}")

if __name__ == "__main__":
    build_addon()
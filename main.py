# encoding: utf-8
import zipfile
import json
import os

# --- v4.1.2 核心修復與版本更新 ---
# 1. 修正嵌套牌組 (Deck::SubDeck) 在移動時，因父路徑變更導致的 ID 查找失敗。
# 2. 優化層級處理邏輯，確保父牌組優先獲得排序前綴，子牌組正確繼承。
# 3. 更新顯示名稱為 Deck_Reorder (v4.1.2)，確保 Anki 介面顯示符合要求。
# 4. 匯出檔案名稱維持為 Deck_Reorder.ankiaddon。

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

I18N = {
    "zh-TW": {
        "menu_name": "⇅ 牌組重排",
        "move_top": "⏫ 移至頂部",
        "move_up": "🔼 上移",
        "move_down": "🔽 下移",
        "move_btm": "⏬ 移至底部",
        "adv_mgr": "🛠️ 進階管理器...",
        "save": "✅ 儲存並套用",
        "title": "Deck_Reorder 管理器 (v4.1.2)",
        "success": "設定已存檔並套用",
        "settings_group": "自動化與介面設定",
        "lang_label": "介面語言:",
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
        "title": "Deck_Reorder Manager (v4.1.2)",
        "success": "Settings saved and applied",
        "settings_group": "Automation & UI Settings",
        "lang_label": "Language:",
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
    if not isinstance(conf, dict): conf = {}
    defaults = {CONF_KEY_LANG: "en", CONF_KEY_POS: "top", CONF_KEY_AUTO: True, CONF_KEY_TARGET_DECK: ""}
    for k, v in defaults.items():
        if k not in conf: conf[k] = v
    return conf

def get_msg(key, lang_override=None):
    lang = lang_override if lang_override else get_current_config().get(CONF_KEY_LANG, "en")
    return I18N.get(lang, I18N["en"]).get(key, key)

def clean_name(name: str) -> str:
    return name.replace(CHAR_0, '').replace(CHAR_1, '')

def is_unsorted(name: str) -> bool:
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
        id_to_clean_full = {d.id: clean_name(d.name) for d in all_decks if d.id != 1}
        
        temp_root = f"__REORDER_{int(time.time())}__"
        for d in all_decks:
            if d.id == 1: continue
            deck = mw.col.decks.get(d.id)
            if deck: mw.col.decks.rename(deck, f"{temp_root}_{d.id}")
        mw.col.decks.save()

        id_to_sort_label = {}
        for counter, did in enumerate(ordered_ids):
            if did not in id_to_clean_full: continue
            prefix = format(counter, '016b').replace('0', CHAR_0).replace('1', CHAR_1)
            single_name = id_to_clean_full[did].split('::')[-1]
            id_to_sort_label[did] = prefix + single_name

        final_tasks = []
        sorted_dids = sorted(id_to_clean_full.keys(), key=lambda did: id_to_clean_full[did].count('::'))
        clean_path_to_id = {v: k for k, v in id_to_clean_full.items()}

        for did in sorted_dids:
            parts = id_to_clean_full[did].split('::')
            new_path_parts = []
            for p in parts:
                original_layer_path = "::".join(parts[:len(new_path_parts)+1])
                layer_id = clean_path_to_id.get(original_layer_path)
                label = id_to_sort_label.get(layer_id, p)
                new_path_parts.append(label)
            
            final_path = "::".join(new_path_parts)
            final_tasks.append((did, final_path))

        final_tasks.sort(key=lambda x: x[1].count('::'))
        for did, final_name in final_tasks:
            tmp_name = f"{temp_root}_{did}"
            deck_obj = mw.col.decks.by_name(tmp_name)
            if deck_obj:
                mw.col.decks.rename(deck_obj, final_name)

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
    
    target_deck_clean = conf.get(CONF_KEY_TARGET_DECK, "")
    if target_deck_clean:
        clean_names_to_raw = {clean_name(d.name): d.name for d in all_d}
        if target_deck_clean in clean_names_to_raw:
            target_raw = clean_names_to_raw[target_deck_clean]
            for d in new_d:
                base_clean = clean_name(d.name)
                if '::' not in base_clean:
                    deck_obj = mw.col.decks.get(d.id)
                    mw.col.decks.rename(deck_obj, f"{target_raw}::{base_clean}")
            mw.col.decks.save()
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
        self.setFixedWidth(480)
        self.setFixedHeight(600)
        self.setup_ui()
        self.update_dialog_texts()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.settings_group = QGroupBox()
        s_lay = QVBoxLayout()
        
        l_row = QHBoxLayout(); self.lang_label = QLabel(); l_row.addWidget(self.lang_label)
        self.lang_combo = QComboBox(); self.lang_combo.addItem("English", "en"); self.lang_combo.addItem("繁體中文", "zh-TW")
        idx_lang = self.lang_combo.findData(self.conf.get(CONF_KEY_LANG, "en"))
        self.lang_combo.setCurrentIndex(idx_lang if idx_lang != -1 else 0)
        self.lang_combo.currentIndexChanged.connect(self.update_dialog_texts)
        l_row.addWidget(self.lang_combo); s_lay.addLayout(l_row)

        self.auto_cb = QCheckBox(); self.auto_cb.setChecked(self.conf.get(CONF_KEY_AUTO, True))
        s_lay.addWidget(self.auto_cb)
        
        t_row = QHBoxLayout(); self.target_deck_label = QLabel(); t_row.addWidget(self.target_deck_label)
        self.target_combo = QComboBox()
        self.target_combo.addItem("", "")
        decks_clean = sorted([clean_name(d.name) for d in mw.col.decks.all_names_and_ids() if d.id != 1])
        for d_name in decks_clean: self.target_combo.addItem(d_name, d_name)
        idx_target = self.target_combo.findData(self.conf.get(CONF_KEY_TARGET_DECK, ""))
        self.target_combo.setCurrentIndex(idx_target if idx_target != -1 else 0)
        t_row.addWidget(self.target_combo); s_lay.addLayout(t_row)

        p_row = QHBoxLayout(); self.new_deck_label = QLabel(); p_row.addWidget(self.new_deck_label)
        self.pos_combo = QComboBox(); self.pos_combo.addItem("", "top"); self.pos_combo.addItem("", "bottom")
        idx_pos = self.pos_combo.findData(self.conf.get(CONF_KEY_POS, "top"))
        self.pos_combo.setCurrentIndex(idx_pos if idx_pos != -1 else 0)
        p_row.addWidget(self.pos_combo); s_lay.addLayout(p_row)
        
        self.settings_group.setLayout(s_lay); self.layout.addWidget(self.settings_group)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.layout.addWidget(self.tree)
        self.btn_save = QPushButton(); self.btn_save.setFixedHeight(45); self.btn_save.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self.save); self.layout.addWidget(self.btn_save)
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
            item = QTreeWidgetItem(parent); item.setText(0, pts[-1]); item.setData(0, Qt.ItemDataRole.UserRole, d.id)
            item.setExpanded(True); nodes['::'.join(pts)] = item

    def save(self):
        final_lang = self.lang_combo.currentData()
        new_conf = {CONF_KEY_LANG: final_lang, CONF_KEY_AUTO: self.auto_cb.isChecked(), CONF_KEY_TARGET_DECK: self.target_combo.currentData(), CONF_KEY_POS: self.pos_combo.currentData()}
        mw.addonManager.writeConfig(__name__, new_conf)
        ids = []
        def traverse(p):
            for i in range(p.childCount()):
                c = p.child(i); ids.append(c.data(0, Qt.ItemDataRole.UserRole)); traverse(c)
        traverse(self.tree.invisibleRootItem())
        apply_order_ultimate(ids)
        tooltip(get_msg("success", final_lang)); self.accept()

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
    action.triggered.connect(lambda: DeckManagerDialog(mw).exec())
    mw.form.menuTools.addAction(action)

gui_hooks.main_window_did_init.append(init)
"""

# 重要：這裡的 name 決定了 Anki 附加元件清單中顯示的名稱，現在包含版本號
MANIFEST = {
    "package": "UltimateDeckReorderPlus",
    "name": "Deck_Reorder (v4.1.2)",
    "mod": 1710850016
}

DEFAULT_CONFIG = {
    "reorder_lang": "en",
    "new_deck_pos": "top",
    "auto_reorder": True,
    "auto_target_deck": ""
}

def build_addon():
    # 檔案名稱保持不變為 Deck_Reorder.ankiaddon
    filename = 'Deck_Reorder.ankiaddon'
    with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('__init__.py', ADDON_CODE.strip())
        zf.writestr('manifest.json', json.dumps(MANIFEST, indent=4, ensure_ascii=False))
        
        # 新增 meta.json：確保 Anki 主程式清單顯示帶有版本號的名稱
        meta_data = {
            "name": MANIFEST["name"],
            "mod": MANIFEST["mod"]
        }
        zf.writestr('meta.json', json.dumps(meta_data, indent=4, ensure_ascii=False))
        
        zf.writestr('config.json', json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False))
    print(f"Build Successful (v4.1.2): {os.path.abspath(filename)}")

if __name__ == "__main__":
    build_addon()
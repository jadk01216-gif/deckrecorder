# encoding: utf-8
import zipfile
import json
import os

# --- v4.2.3 核心修復與無限位數演算法 ---
# 1. 演算法 2.0: 導入 Elias Gamma 變體編碼，實現理論上「無限位數」的動態隱形字元排序。
# 2. 順水推舟法: 完美解決嵌套牌組問題。順應 Anki 原生「改母連動子」的機制，採 Top-Down 即時讀取與覆寫。
# 3. 修復母牌組拖曳: 客製化 ReorderTreeWidget 嚴格限制僅能進行同層級的兄弟節點重排。
# 4. 修復快捷移動: 使 quick_move 具備「區塊意識 (Block-aware)」，完整跳躍子牌組群集。
# 5. [v4.2.2] 動態語系切換: 儲存設定時，立即同步更新 Anki「工具」選單中的管理器名稱。
# 6. [v4.2.3] 臭蟲修復: 補回遺失的 load_tree 渲染函式。

ADDON_CODE = """
import time
from aqt import mw
from aqt.qt import *
from aqt.utils import tooltip
from aqt import gui_hooks

# --- Constants ---
CHAR_0 = '\\u200b' # A (較小)
CHAR_1 = '\\u200c' # B (較大)
CONF_KEY_LANG = "reorder_lang" 
CONF_KEY_POS = "new_deck_pos" 
CONF_KEY_AUTO = "auto_reorder" 
CONF_KEY_TARGET_DECK = "auto_target_deck"

_is_reordering = False
_tools_action = None

I18N = {
    "zh-TW": {
        "menu_name": "⇅ 牌組重排",
        "move_top": "⏫ 移至頂部",
        "move_up": "🔼 上移",
        "move_down": "🔽 下移",
        "move_btm": "⏬ 移至底部",
        "adv_mgr": "🛠️ 進階管理器...",
        "save": "✅ 儲存並套用",
        "title": "Deck_Reorder 管理器 (v4.2.3)",
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
        "title": "Deck_Reorder Manager (v4.2.3)",
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

def encode_infinite(n: int) -> str:
    n += 1 
    b = bin(n)[2:] 
    length = len(b) - 1
    prefix = (CHAR_1 * length) + CHAR_0
    suffix = b[1:].replace('0', CHAR_0).replace('1', CHAR_1)
    return prefix + suffix

def apply_order_ultimate(ordered_ids):
    global _is_reordering
    if not ordered_ids or _is_reordering: return
    _is_reordering = True
    try:
        mw.checkpoint("Deck Reorder")
        mw.col.modSchema(check=False)
        
        all_decks = list(mw.col.decks.all_names_and_ids())
        
        id_to_clean_name = {d.id: clean_name(d.name) for d in all_decks if d.id != 1}
        clean_path_to_id = {clean_name(d.name): d.id for d in all_decks if d.id != 1}
        
        id_to_new_basename = {}
        for counter, did in enumerate(ordered_ids):
            if did not in id_to_clean_name: continue
            prefix = encode_infinite(counter)
            old_basename = id_to_clean_name[did].split('::')[-1]
            id_to_new_basename[did] = prefix + old_basename

        final_tasks = {}
        for did, clean_full_name in id_to_clean_name.items():
            parts = clean_full_name.split('::')
            new_path_parts = []
            for i in range(len(parts)):
                current_layer_clean = "::".join(parts[:i+1])
                layer_id = clean_path_to_id.get(current_layer_clean)
                
                if layer_id in id_to_new_basename:
                    new_path_parts.append(id_to_new_basename[layer_id])
                else:
                    new_path_parts.append(parts[i])
            
            final_tasks[did] = "::".join(new_path_parts)

        sorted_dids_asc = sorted(id_to_clean_name.keys(), key=lambda did: id_to_clean_name[did].count('::'))
        
        for did in sorted_dids_asc:
            deck = mw.col.decks.get(did)
            if not deck: continue
            
            final_name = final_tasks.get(did)
            if deck['name'] != final_name:
                mw.col.decks.rename(deck, final_name)

        mw.col.decks.save()
        mw.reset()
        if mw.deckBrowser: mw.deckBrowser.refresh()
    except Exception as e:
        print(f"Deck Reorder Error: {e}")
        tooltip(f"Deck Reorder 發生錯誤: {e}")
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
    
    node_map = {}
    for d in all_d:
        node_map[d.id] = {'id': d.id, 'c_name': clean_name(d.name), 'children': []}
        
    root_nodes = []
    
    for d in all_d:
        node = node_map[d.id]
        parts = node['c_name'].split('::')
        if len(parts) > 1:
            parent_path = '::'.join(parts[:-1])
            parent_node = next((n for n in node_map.values() if n['c_name'] == parent_path), None)
            if parent_node:
                parent_node['children'].append(node)
            else:
                root_nodes.append(node)
        else:
            root_nodes.append(node)
            
    if did not in node_map: return
    
    target_node = node_map[did]
    parts = target_node['c_name'].split('::')
    
    if len(parts) > 1:
        parent_path = '::'.join(parts[:-1])
        parent_node = next((n for n in node_map.values() if n['c_name'] == parent_path), None)
        siblings = parent_node['children'] if parent_node else root_nodes
    else:
        siblings = root_nodes
        
    idx = next((i for i, sib in enumerate(siblings) if sib['id'] == did), -1)
    if idx == -1: return
    
    if op == "up" and idx > 0:
        siblings[idx], siblings[idx-1] = siblings[idx-1], siblings[idx]
    elif op == "down" and idx < len(siblings) - 1:
        siblings[idx], siblings[idx+1] = siblings[idx+1], siblings[idx]
    elif op == "top" and idx > 0:
        sib = siblings.pop(idx)
        siblings.insert(0, sib)
    elif op == "btm" and idx < len(siblings) - 1:
        sib = siblings.pop(idx)
        siblings.append(sib)
        
    flat_ids = []
    def traverse(nodes):
        for n in nodes:
            flat_ids.append(n['id'])
            traverse(n['children'])
            
    traverse(root_nodes)
    apply_order_ultimate(flat_ids)
    tooltip(get_msg("success"))

class ReorderTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        dragged_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        if not dragged_item or not target_item:
            return

        pos = self.dropIndicatorPosition()
        
        if pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            event.ignore()
            return

        intended_parent = target_item.parent() if target_item else self.invisibleRootItem()
        drag_parent = dragged_item.parent() if dragged_item else self.invisibleRootItem()

        if drag_parent != intended_parent:
            event.ignore()
        else:
            event.accept()

    def dropEvent(self, event):
        dragged_item = self.currentItem()
        target_item = self.itemAt(event.pos())
        if not dragged_item or not target_item:
            return super().dropEvent(event)

        pos = self.dropIndicatorPosition()
        if pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            event.ignore()
            return

        intended_parent = target_item.parent() if target_item else self.invisibleRootItem()
        drag_parent = dragged_item.parent() if dragged_item else self.invisibleRootItem()

        if drag_parent != intended_parent:
            event.ignore()
            return

        super().dropEvent(event)

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
        
        self.tree = ReorderTreeWidget() 
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

    # [v4.2.3 修復] 補回在精簡代碼時不小心刪除的樹狀圖渲染功能
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
        new_conf = {CONF_KEY_LANG: final_lang, CONF_KEY_AUTO: self.auto_cb.isChecked(), CONF_KEY_TARGET_DECK: self.target_combo.currentData(), CONF_KEY_POS: self.pos_combo.currentData()}
        mw.addonManager.writeConfig(__name__, new_conf)
        
        global _tools_action
        if _tools_action is not None:
            _tools_action.setText(get_msg("adv_mgr", final_lang))
            
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
    global _tools_action
    gui_hooks.deck_browser_will_show_options_menu.append(on_deck_menu)
    gui_hooks.deck_browser_did_render.append(check_auto)
    
    _tools_action = QAction(get_msg("adv_mgr"), mw)
    _tools_action.triggered.connect(lambda: DeckManagerDialog(mw).exec())
    mw.form.menuTools.addAction(_tools_action)

gui_hooks.main_window_did_init.append(init)
"""

# MANIFEST 更新至 v4.2.3
MANIFEST = {
    "package": "UltimateDeckReorderPlus",
    "name": "Deck_Reorder (v4.2.3)",
    "mod": 1710850023
}

DEFAULT_CONFIG = {
    "reorder_lang": "en",
    "new_deck_pos": "top",
    "auto_reorder": True,
    "auto_target_deck": ""
}

def build_addon():
    filename = 'Deck_Reorder.ankiaddon'
    with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('__init__.py', ADDON_CODE.strip())
        zf.writestr('manifest.json', json.dumps(MANIFEST, indent=4, ensure_ascii=False))
        meta_data = {"name": MANIFEST["name"], "mod": MANIFEST["mod"]}
        zf.writestr('meta.json', json.dumps(meta_data, indent=4, ensure_ascii=False))
        zf.writestr('config.json', json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False))
    print(f"Build Successful (v4.2.3): {os.path.abspath(filename)}")

if __name__ == "__main__":
    build_addon()
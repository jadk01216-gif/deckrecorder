# encoding: utf-8
import zipfile
import json
import os

# --- v4.4.0 完美自由拖曳版 ---
# 1. 演算法 2.0: 導入 Elias Gamma 編碼，實現「無限位數」的動態隱形字元排序。
# 2. 順水推舟法: 完美解決嵌套牌組問題，Top-Down 即時讀取與覆寫。
# 3. 智能拖曳攔截: 允許原生放入子牌組，但攔截獨立拖曳重排，並顯示開發中提示。
# 4. [v4.3.9] 啟用 Qt 原生 InternalMove：移除所有自訂拖曳事件覆寫，交由 Qt 內建處理。
# 5. [v4.3.9] 不顯示藍線/藍框：setDropIndicatorShown(False)，視覺乾淨；層級變更請用進階管理器或右鍵選單。
# 6. [v4.3.9] 修正移置母牌組: 改用 raw name (含隱形字元) 作為目標父層路徑，避免 Anki rename 找不到父層而重建母牌組。
# 7. [v4.3.9] 新增「移出母牌組 N 層」: 右鍵選單與進階管理器均可使用，已在最上層時顯示提示，輸入超出深度時警告。
# 8. [v4.3.9] 進階管理器新增藍線/藍框拖曳提示（含最上/最下層邊界）、復原 / 重做功能。首頁不受影響。
# 9. [v4.3.9] 進階管理器新增重新命名與刪除功能；刪除在儲存時才真正寫入 Anki。
# 10. [v4.3.9] 移除「自動處理並重排」勾選框；新增「Anki 預設」選項至排序位置與父牌組設定。
# 11. [v4.4.0] 右鍵選單智能停用：已在頂部時停用「頂部」/「上移」，已在底部時停用「底部」/「下移」，已在最上層時停用「移出母牌組」；無法移動時顯示 tooltip 提示。

ADDON_CODE = """
from aqt import mw
from aqt.qt import *
from aqt.utils import tooltip
from aqt import gui_hooks

# --- Constants ---
CHAR_0 = '\\u200b' # A (較小)
CHAR_1 = '\\u200c' # B (較大)
CONF_KEY_LANG = "reorder_lang" 
CONF_KEY_POS = "new_deck_pos"
CONF_KEY_TARGET_DECK = "auto_target_deck"

_is_reordering = False
_tools_action = None

I18N = {
    "zh-TW": {
        "menu_name": "⇅ 牌組重排",
        "move_top": "⏫ 頂部",
        "move_up": "🔼 上移",
        "move_down": "🔽 下移",
        "move_btm": "⏬ 底部",
        "move_steps_menu": "🔢 移動自訂格數...",
        "move_parent": "📂 移置母牌組...",
        "adv_mgr": "🛠️ 進階管理器...",
        "save": "✅ 儲存並套用",
        "help_btn": "📖 用法教學",
        "title": "Deck_Reorder 管理器 (v4.4.0)",
        "success": "設定已存檔並套用",
        "settings_group": "自動化與介面設定",
        "lang_label": "介面語言:",
        "new_deck_label": "新牌組排序位置:",
        "target_deck_label": "預設放入的父牌組:",
        "target_root": "< 最上層 (無) >",
        "target_anki": "< Anki 預設 (不移動) >",
        "pos_top": "最上面",
        "pos_bottom": "最下面",
        "pos_anki": "< Anki 預設 >",
        "dialog_move_steps": "🔢 移動 N 格",
        "dialog_move_prompt_title": "移動格數",
        "dialog_move_prompt_desc": "請輸入要移動的格數\\n(正數往下，負數往上):",
        "dialog_no_selection": "請先在下方樹狀圖中選取一個牌組！",
        "dialog_parent_btn": "📂 移置母牌組",
        "dialog_parent_title": "變更母牌組",
        "dialog_parent_desc": "請選擇新的目標牌組 (支援搜尋):",
        "dialog_parent_root": "< 獨立出來 (最上層) >",
        "search_placeholder": "🔍 搜尋牌組名稱...",
        "warn_out_of_bounds": "移動步數超出範圍！\\n只能在 0 到 {max_idx} 之間移動。",
        "warn_cannot_move": "已經在最邊緣，無法再移動了！",
        "unparent_btn": "⬆️ 移出母牌組",
        "unparent_menu": "⬆️ 移出母牌組 N 層...",
        "unparent_prompt_title": "移出母牌組",
        "unparent_prompt_desc": "請輸入要移出幾層母牌組\\n(1 = 往上一層，2 = 往上兩層，以此類推):",
        "warn_already_root": "此牌組已經在最上層，無法再移出！",
        "undo_btn": "↩ 復原",
        "redo_btn": "↪ 重做",
        "rename_btn": "✏️ 重新命名",
        "rename_title": "重新命名牌組",
        "rename_desc": "請輸入新的牌組名稱:",
        "rename_empty": "名稱不能為空白！",
        "rename_has_sep": "名稱不可包含 :: 符號！",
        "delete_btn": "🗑️ 刪除",
        "delete_confirm_title": "確認刪除",
        "delete_confirm_desc": "確定要刪除「{name}」及其所有子牌組嗎？\\n此操作套用後無法復原！",
        "warn_unparent_exceed": "超出層數！此牌組目前有 {depth} 層，最多只能移出 {depth} 層。",
        "tree_search_placeholder": "🔍 搜尋牌組（即時過濾）...",
        "tutorial_title": "Deck_Reorder 使用教學",
        "tutorial_text": "【拖曳排序】\\n支援同層牌組的滑鼠拖曳排序（無提示線/藍框干擾）。\\n若要變更牌組的上下層級，請使用「📂 移置母牌組」按鈕或右鍵選單。\\n\\n【移出母牌組】\\n點擊「⬆️ 移出母牌組」可將牌組向上移出指定層數。輸入 1 往上一層，2 往上兩層，以此類推。若已在最上層會顯示提示。\\n\\n【自訂格數】\\n輸入正數往下移，輸入負數往上移。\\n\\n【移置母牌組】\\n點擊「📂 移置母牌組」可搜尋並選擇新的父牌組，支援關鍵字搜尋。\\n\\n【自動排序與歸檔】\\n上方可設定當匯入新牌組時，自動幫你把它丟到列表的最上面或最下面，甚至自動塞進特定的預設父牌組中。"
    },
    "en": {
        "menu_name": "⇅ Deck Reorder",
        "move_top": "⏫ Top",
        "move_up": "🔼 Up",
        "move_down": "🔽 Down",
        "move_btm": "⏬ Bottom",
        "move_steps_menu": "🔢 Move N Steps...",
        "move_parent": "📂 Change Parent...",
        "adv_mgr": "🛠️ Advanced Manager...",
        "save": "✅ Save and Apply",
        "help_btn": "📖 Help / Tutorial",
        "title": "Deck_Reorder Manager (v4.4.0)",
        "success": "Settings saved and applied",
        "settings_group": "Automation & UI Settings",
        "lang_label": "Language:",
        "new_deck_label": "New Deck Position:",
        "target_deck_label": "Default Parent Deck:",
        "target_root": "< Root (None) >",
        "target_anki": "< Anki Default (no move) >",
        "pos_top": "Top",
        "pos_bottom": "Bottom",
        "pos_anki": "< Anki Default >",
        "dialog_move_steps": "🔢 N Steps",
        "dialog_move_prompt_title": "Move Steps",
        "dialog_move_prompt_desc": "Enter steps to move\\n(Positive for down, Negative for up):",
        "dialog_no_selection": "Please select a deck from the tree first!",
        "dialog_parent_btn": "📂 Set Parent",
        "dialog_parent_title": "Change Parent Deck",
        "dialog_parent_desc": "Select new target deck (Searchable):",
        "dialog_parent_root": "< Make Independent (Root) >",
        "search_placeholder": "🔍 Search deck name...",
        "warn_out_of_bounds": "Steps out of bounds!\\nCan only move between 0 and {max_idx}.",
        "warn_cannot_move": "Already at the edge, cannot move further!",
        "unparent_btn": "⬆️ Unparent",
        "unparent_menu": "⬆️ Unparent N Levels...",
        "unparent_prompt_title": "Unparent Deck",
        "unparent_prompt_desc": "Enter how many parent levels to move up\\n(1 = one level up, 2 = two levels up, etc.):",
        "warn_already_root": "This deck is already at the root level, cannot unparent further!",
        "undo_btn": "↩ Undo",
        "redo_btn": "↪ Redo",
        "rename_btn": "✏️ Rename",
        "rename_title": "Rename Deck",
        "rename_desc": "Enter new deck name:",
        "rename_empty": "Name cannot be empty!",
        "rename_has_sep": "Name cannot contain :: separator!",
        "delete_btn": "🗑️ Delete",
        "delete_confirm_title": "Confirm Delete",
        "delete_confirm_desc": "Delete {name} and all its sub-decks?\\nThis cannot be undone after saving!",
        "warn_unparent_exceed": "Exceeds depth! This deck has {depth} level(s), maximum is {depth}.",
        "tree_search_placeholder": "🔍 Search decks (live filter)...",
        "tutorial_title": "Deck_Reorder Tutorial",
        "tutorial_text": "[Drag & Drop]\\nSupports same-level drag-and-drop reordering (no blue line/box indicators).\\nTo change a deck's hierarchy, use the '📂 Set Parent' button or the right-click menu.\\n\\n[Unparent]\\nClick '⬆️ Unparent' to move a deck up by N parent levels. Enter 1 to go up one level, 2 for two levels, etc. A warning is shown if the deck is already at the root.\\n\\n[Custom Steps]\\nPositive number moves the deck down, negative moves it up.\\n\\n[Change Parent]\\nTo move a deck using a menu, click '📂 Set Parent' (supports keyword search).\\n\\n[Auto-Sort & Archive]\\nConfigure the settings above to automatically place newly imported decks at the Top or Bottom, or even auto-route them into a specific Default Parent Deck."
    }
}

def get_current_config():
    conf = mw.addonManager.getConfig(__name__)
    if not isinstance(conf, dict): conf = {}
    defaults = {CONF_KEY_LANG: "en", CONF_KEY_POS: "anki", CONF_KEY_TARGET_DECK: "anki"}
    for k, v in defaults.items():
        if k not in conf: conf[k] = v
    return conf

def get_msg(key, lang_override=None, **kwargs):
    lang = lang_override if lang_override else get_current_config().get(CONF_KEY_LANG, "en")
    msg = I18N.get(lang, I18N["en"]).get(key, key)
    if kwargs:
        return msg.format(**kwargs)
    return msg

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

def apply_order_ultimate(ordered_ids, forced_clean_paths=None):
    global _is_reordering
    if not ordered_ids or _is_reordering: return
    _is_reordering = True
    try:
        mw.checkpoint("Deck Reorder")
        mw.col.modSchema(check=False)
        all_decks = list(mw.col.decks.all_names_and_ids())
        id_to_clean_name = {d.id: clean_name(d.name) for d in all_decks if d.id != 1}
        
        if forced_clean_paths:
            for did, path in forced_clean_paths.items():
                if did in id_to_clean_name:
                    id_to_clean_name[did] = path

        clean_path_to_id = {path: did for did, path in id_to_clean_name.items()}
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
    pos    = conf.get(CONF_KEY_POS, "anki")
    target = conf.get(CONF_KEY_TARGET_DECK, "anki")
    if pos == "anki" and target == "anki": return

    all_d = [d for d in mw.col.decks.all_names_and_ids() if d.id != 1]
    new_d = [d for d in all_d if is_unsorted(d.name)]
    if not new_d: return

    if target != "anki" and target:
        clean_names_to_raw = {clean_name(d.name): d.name for d in all_d}
        if target in clean_names_to_raw:
            target_raw = clean_names_to_raw[target]
            for d in new_d:
                base_clean = clean_name(d.name)
                if '::' not in base_clean:
                    deck_obj = mw.col.decks.get(d.id)
                    mw.col.decks.rename(deck_obj, f"{target_raw}::{base_clean}")
            mw.col.decks.save()
            all_d = [d for d in mw.col.decks.all_names_and_ids() if d.id != 1]
            new_d = [d for d in all_d if is_unsorted(d.name)]

    if pos == "anki": return
    ids = [d.id for d in sorted(all_d, key=lambda d: d.name)]
    n_ids = [d.id for d in new_d]
    for nid in n_ids:
        if nid in ids: ids.remove(nid)
    ids = (n_ids + ids) if pos == "top" else (ids + n_ids)
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
            if parent_node: parent_node['children'].append(node)
            else: root_nodes.append(node)
        else: root_nodes.append(node)
            
    if did not in node_map: return
    target_node = node_map[did]
    parts = target_node['c_name'].split('::')
    
    if len(parts) > 1:
        parent_path = '::'.join(parts[:-1])
        parent_node = next((n for n in node_map.values() if n['c_name'] == parent_path), None)
        siblings = parent_node['children'] if parent_node else root_nodes
    else: siblings = root_nodes
        
    idx = next((i for i, sib in enumerate(siblings) if sib['id'] == did), -1)
    if idx == -1: return
    
    moved = False
    if op == "up" and idx > 0:
        siblings[idx], siblings[idx-1] = siblings[idx-1], siblings[idx]; moved = True
    elif op == "down" and idx < len(siblings) - 1:
        siblings[idx], siblings[idx+1] = siblings[idx+1], siblings[idx]; moved = True
    elif op == "top" and idx > 0:
        sib = siblings.pop(idx); siblings.insert(0, sib); moved = True
    elif op == "btm" and idx < len(siblings) - 1:
        sib = siblings.pop(idx); siblings.append(sib); moved = True

    if not moved:
        tooltip(get_msg("warn_cannot_move")); return

    flat_ids = []
    def traverse(nodes):
        for n in nodes:
            flat_ids.append(n['id']); traverse(n['children'])
    traverse(root_nodes)
    apply_order_ultimate(flat_ids)
    tooltip(get_msg("success"))

def quick_move_steps(did):
    lang = get_current_config().get(CONF_KEY_LANG, "en")
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
            if parent_node: parent_node['children'].append(node)
            else: root_nodes.append(node)
        else: root_nodes.append(node)
            
    if did not in node_map: return
    target_node = node_map[did]
    parts = target_node['c_name'].split('::')
    
    if len(parts) > 1:
        parent_path = '::'.join(parts[:-1])
        parent_node = next((n for n in node_map.values() if n['c_name'] == parent_path), None)
        siblings = parent_node['children'] if parent_node else root_nodes
    else: siblings = root_nodes
        
    idx = next((i for i, sib in enumerate(siblings) if sib['id'] == did), -1)
    if idx == -1: return
    
    count = len(siblings)
    title = get_msg("dialog_move_prompt_title", lang)
    desc = get_msg("dialog_move_prompt_desc", lang)
    
    steps, ok = QInputDialog.getInt(mw, title, desc, 0, -999, 999, 1)
    if not ok or steps == 0: return
    
    intended_idx = idx + steps
    if intended_idx < 0 or intended_idx >= count:
        QMessageBox.warning(mw, "Warning", get_msg("warn_out_of_bounds", lang, max_idx=count-1))
        return
        
    sib = siblings.pop(idx)
    siblings.insert(intended_idx, sib)
    
    flat_ids = []
    def traverse(nodes):
        for n in nodes:
            flat_ids.append(n['id']); traverse(n['children'])
    traverse(root_nodes)
    apply_order_ultimate(flat_ids)
    tooltip(get_msg("success", lang))

class SearchableDeckDialog(QDialog):
    def __init__(self, parent, title, desc, items, placeholder="Search..."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(450, 500)
        layout = QVBoxLayout(self)

        self.label = QLabel(desc)
        layout.addWidget(self.label)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(placeholder)
        self.search_bar.textChanged.connect(self.filter_items)
        layout.addWidget(self.search_bar)

        self.list_widget = QListWidget()
        for text, data in items:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.list_widget.itemDoubleClicked.connect(self.accept)

    def filter_items(self, text):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def get_selected_data(self):
        item = self.list_widget.currentItem()
        if item: return item.data(Qt.ItemDataRole.UserRole)
        return None

def quick_change_parent(did):
    lang = get_current_config().get(CONF_KEY_LANG, "en")

    # 先讀取含隱形字元的原始資料，建立 clean->raw 對照表
    all_d_fresh = [d for d in mw.col.decks.all_names_and_ids() if d.id != 1]
    id_to_raw = {d.id: d.name for d in all_d_fresh}
    clean_to_raw = {clean_name(d.name): d.name for d in all_d_fresh}

    target_deck_info = next((d for d in all_d_fresh if d.id == did), None)
    if not target_deck_info: return

    target_clean = clean_name(target_deck_info.name)
    root_name = get_msg("dialog_parent_root", lang)

    # valid_targets: (顯示文字, clean_name)
    valid_targets = [(f"🌟 {root_name}", "")]
    for d in sorted(all_d_fresh, key=lambda d: clean_name(d.name)):
        c_name = clean_name(d.name)
        if c_name == target_clean or c_name.startswith(target_clean + "::"): continue
        valid_targets.append((c_name, c_name))

    title = get_msg("dialog_parent_title", lang)
    desc = get_msg("dialog_parent_desc", lang)
    placeholder = get_msg("search_placeholder", lang)

    dialog = SearchableDeckDialog(mw, title, desc, valid_targets, placeholder)
    if not dialog.exec(): return

    new_parent_clean = dialog.get_selected_data()
    if new_parent_clean is None: return

    # 關鍵修正：將目標父牌組的 clean name 轉回含隱形字元的 raw name
    # 這樣 Anki rename 時才能正確識別父層，不會重新建立空的母牌組
    new_parent_raw = clean_to_raw.get(new_parent_clean, "") if new_parent_clean else ""

    mw.checkpoint("Change Deck Parent")
    mw.col.modSchema(check=False)

    # 被移動牌組自身的 raw basename（含隱形字元排序前綴）
    target_raw_basename = id_to_raw[did].split('::')[-1]
    # 組出新的自身完整 raw 路徑
    new_self_raw = f"{new_parent_raw}::{target_raw_basename}" if new_parent_raw else target_raw_basename

    # 找出所有受影響牌組（自身 + 子牌組），由淺到深排序
    affected = sorted(
        [d for d in all_d_fresh if clean_name(d.name) == target_clean or clean_name(d.name).startswith(target_clean + "::")],
        key=lambda d: clean_name(d.name).count('::')
    )

    for d in affected:
        c = clean_name(d.name)
        # 相對於被移動牌組的子路徑，例如 "" 或 "::child" 或 "::child::grandchild"
        suffix_clean = c[len(target_clean):]

        # 保留子牌組自身的 raw basename（含隱形字元排序前綴）
        raw_basename = id_to_raw[d.id].split('::')[-1]

        if suffix_clean:
            # suffix_clean 形如 "::child::grandchild"
            # 中間層（child）只需 clean name，Anki 會自動對應到已存在的 raw 層
            inner_parts = suffix_clean.lstrip('::').split('::')
            if len(inner_parts) > 1:
                middle = '::'.join(inner_parts[:-1])
                final_name = f"{new_self_raw}::{middle}::{raw_basename}"
            else:
                final_name = f"{new_self_raw}::{raw_basename}"
        else:
            final_name = new_self_raw

        deck_obj = mw.col.decks.get(d.id)
        if not deck_obj: continue
        if deck_obj['name'] != final_name:
            mw.col.decks.rename(deck_obj, final_name)

    mw.col.decks.save()
    mw.reset()
    if mw.deckBrowser: mw.deckBrowser.refresh()
    tooltip(get_msg("success", lang))


def quick_unparent(did):
    # 將指定牌組往上移出 N 層母牌組 (右鍵選單用)
    lang = get_current_config().get(CONF_KEY_LANG, "en")
    all_d_fresh = [d for d in mw.col.decks.all_names_and_ids() if d.id != 1]
    target_info = next((d for d in all_d_fresh if d.id == did), None)
    if not target_info: return

    target_clean = clean_name(target_info.name)
    current_depth = target_clean.count('::')

    if current_depth == 0:
        QMessageBox.warning(mw, "Warning", get_msg("warn_already_root", lang))
        return

    title = get_msg("unparent_prompt_title", lang)
    desc = get_msg("unparent_prompt_desc", lang)
    levels, ok = QInputDialog.getInt(mw, title, desc, 1, 1, 999, 1)
    if not ok: return

    if levels > current_depth:
        QMessageBox.warning(mw, "Warning", get_msg("warn_unparent_exceed", lang, depth=current_depth))
        return

    id_to_raw = {d.id: d.name for d in all_d_fresh}
    clean_to_raw = {clean_name(d.name): d.name for d in all_d_fresh}

    parts = target_clean.split('::')
    ancestor_parts = parts[:-1]  # 不含自己，長度 = current_depth
    new_parent_parts = ancestor_parts[:current_depth - levels]  # 往上移 levels 層
    new_parent_clean = '::'.join(new_parent_parts)
    new_parent_raw = clean_to_raw.get(new_parent_clean, "") if new_parent_clean else ""

    target_raw_basename = id_to_raw[did].split('::')[-1]
    new_self_raw = f"{new_parent_raw}::{target_raw_basename}" if new_parent_raw else target_raw_basename

    affected = sorted(
        [d for d in all_d_fresh if clean_name(d.name) == target_clean or clean_name(d.name).startswith(target_clean + '::')],
        key=lambda d: clean_name(d.name).count('::')
    )

    mw.checkpoint("Unparent Deck")
    mw.col.modSchema(check=False)

    for d in affected:
        c = clean_name(d.name)
        suffix_clean = c[len(target_clean):]
        raw_basename = id_to_raw[d.id].split('::')[-1]
        if suffix_clean:
            inner_parts = suffix_clean.lstrip('::').split('::')
            if len(inner_parts) > 1:
                middle = '::'.join(inner_parts[:-1])
                final_name = f"{new_self_raw}::{middle}::{raw_basename}"
            else:
                final_name = f"{new_self_raw}::{raw_basename}"
        else:
            final_name = new_self_raw
        deck_obj = mw.col.decks.get(d.id)
        if not deck_obj: continue
        if deck_obj['name'] != final_name:
            mw.col.decks.rename(deck_obj, final_name)

    mw.col.decks.save()
    mw.reset()
    if mw.deckBrowser: mw.deckBrowser.refresh()
    tooltip(get_msg("success", lang))

# 首頁用：拖曳僅限同層排序，不顯示藍線/藍框
class ReorderTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(False)

# 進階管理器用：顯示藍線/藍框 (含最上/最下層)，drop 後發出 signal 供 undo stack 使用
# 使用 DragDrop 模式以解決 InternalMove 在邊界無法顯示藍線的問題
class AdvancedTreeWidget(ReorderTreeWidget):
    drop_performed = pyqtSignal()   # 拖曳完成後發出
    drag_started   = pyqtSignal()   # 拖曳開始前發出 (用於存快照)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def startDrag(self, supportedActions):
        self.drag_started.emit()
        super().startDrag(supportedActions)

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self:
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.source() is not self:
            event.ignore()
            return
        dragged = self.currentItem()
        if not dragged:
            event.ignore()
            return
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        target = self.itemAt(pos)
        indicator = self.dropIndicatorPosition()
        DropPos = QAbstractItemView.DropIndicatorPosition
        old_parent = dragged.parent() or self.invisibleRootItem()
        old_parent.takeChild(old_parent.indexOfChild(dragged))
        if target is None or target is dragged:
            self.invisibleRootItem().addChild(dragged)
        elif indicator == DropPos.OnItem:
            target.addChild(dragged)
            target.setExpanded(True)
        elif indicator == DropPos.AboveItem:
            new_parent = target.parent() or self.invisibleRootItem()
            new_parent.insertChild(new_parent.indexOfChild(target), dragged)
        elif indicator == DropPos.BelowItem:
            new_parent = target.parent() or self.invisibleRootItem()
            new_parent.insertChild(new_parent.indexOfChild(target) + 1, dragged)
        else:
            self.invisibleRootItem().addChild(dragged)
        self.setCurrentItem(dragged)
        event.acceptProposedAction()
        self.drop_performed.emit()

class DeckManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conf = get_current_config()
        self._undo_stack = []   # list of snapshots (before each mutation)
        self._redo_stack = []
        self.resize(600, 680)
        self.setup_ui()
        self.update_dialog_texts()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.settings_group = QGroupBox()
        s_lay = QVBoxLayout()
        
        l_row = QHBoxLayout(); self.lang_label = QLabel(); l_row.addWidget(self.lang_label)
        self.lang_combo = QComboBox(); self.lang_combo.addItem("English", "en"); self.lang_combo.addItem("繁體中文", "zh-TW")
        idx_lang = self.lang_combo.findData(self.conf.get(CONF_KEY_LANG, "en"))
        self.lang_combo.setCurrentIndex(idx_lang if idx_lang != -1 else 0)
        self.lang_combo.currentIndexChanged.connect(self.update_dialog_texts)
        l_row.addWidget(self.lang_combo); s_lay.addLayout(l_row)

        t_row = QHBoxLayout(); self.target_deck_label = QLabel(); t_row.addWidget(self.target_deck_label)
        self.target_combo = QComboBox()
        self.target_combo.addItem("", "anki")  # Anki 預設
        self.target_combo.addItem("", "")       # 最上層 (無)
        decks_clean = sorted([clean_name(d.name) for d in mw.col.decks.all_names_and_ids() if d.id != 1])
        for d_name in decks_clean: self.target_combo.addItem(d_name, d_name)
        idx_target = self.target_combo.findData(self.conf.get(CONF_KEY_TARGET_DECK, "anki"))
        self.target_combo.setCurrentIndex(idx_target if idx_target != -1 else 0)
        t_row.addWidget(self.target_combo); s_lay.addLayout(t_row)

        p_row = QHBoxLayout(); self.new_deck_label = QLabel(); p_row.addWidget(self.new_deck_label)
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("", "anki")    # Anki 預設
        self.pos_combo.addItem("", "top")
        self.pos_combo.addItem("", "bottom")
        idx_pos = self.pos_combo.findData(self.conf.get(CONF_KEY_POS, "anki"))
        self.pos_combo.setCurrentIndex(idx_pos if idx_pos != -1 else 0)
        p_row.addWidget(self.pos_combo); s_lay.addLayout(p_row)
        
        self.settings_group.setLayout(s_lay); self.main_layout.addWidget(self.settings_group)
        
        self.btn_layout = QHBoxLayout()
        self.btn_top = QPushButton(); self.btn_top.clicked.connect(lambda: self.move_item_in_tree("top"))
        self.btn_up = QPushButton(); self.btn_up.clicked.connect(lambda: self.move_item_in_tree("up"))
        self.btn_down = QPushButton(); self.btn_down.clicked.connect(lambda: self.move_item_in_tree("down"))
        self.btn_btm = QPushButton(); self.btn_btm.clicked.connect(lambda: self.move_item_in_tree("btm"))
        self.btn_steps = QPushButton(); self.btn_steps.clicked.connect(lambda: self.move_item_in_tree("steps"))
        self.btn_parent = QPushButton(); self.btn_parent.clicked.connect(self.change_parent_of_item)
        self.btn_unparent = QPushButton(); self.btn_unparent.clicked.connect(self.unparent_item_in_tree)
        self.btn_rename = QPushButton(); self.btn_rename.clicked.connect(self.rename_item_in_tree)
        self.btn_delete = QPushButton(); self.btn_delete.clicked.connect(self.delete_item_in_tree)
        self.btn_delete.setStyleSheet("color: #c0392b;")
        
        self.btn_layout.addWidget(self.btn_top)
        self.btn_layout.addWidget(self.btn_up)
        self.btn_layout.addWidget(self.btn_down)
        self.btn_layout.addWidget(self.btn_btm)
        self.btn_layout.addWidget(self.btn_steps)
        self.btn_layout.addWidget(self.btn_parent)
        self.btn_layout.addWidget(self.btn_unparent)
        self.btn_layout.addWidget(self.btn_rename)
        self.btn_layout.addWidget(self.btn_delete)
        self.main_layout.addLayout(self.btn_layout)

        self.undo_redo_layout = QHBoxLayout()
        self.btn_undo = QPushButton(); self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton(); self.btn_redo.clicked.connect(self.redo)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)
        self.undo_redo_layout.addWidget(self.btn_undo)
        self.undo_redo_layout.addWidget(self.btn_redo)
        self.main_layout.addLayout(self.undo_redo_layout)

        self.tree_search = QLineEdit()
        self.tree_search.textChanged.connect(self.filter_tree)
        self.main_layout.addWidget(self.tree_search)

        self.tree = AdvancedTreeWidget()
        self.tree.drag_started.connect(self._on_drag_started)
        self.tree.drop_performed.connect(self._on_drop_performed)
        self.main_layout.addWidget(self.tree)
        
        bottom_layout = QHBoxLayout()
        self.btn_help = QPushButton()
        self.btn_help.setFixedHeight(45)
        self.btn_help.clicked.connect(self.show_tutorial)
        
        self.btn_save = QPushButton()
        self.btn_save.setFixedHeight(45)
        self.btn_save.setStyleSheet("background: #27ae60; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self.save)
        
        bottom_layout.addWidget(self.btn_help, 1) 
        bottom_layout.addWidget(self.btn_save, 3) 
        self.main_layout.addLayout(bottom_layout)
        
        self.load_tree()

    def update_dialog_texts(self):
        lang = self.lang_combo.currentData()
        self.setWindowTitle(get_msg("title", lang))
        self.settings_group.setTitle(get_msg("settings_group", lang))
        self.lang_label.setText(get_msg("lang_label", lang))
        self.target_deck_label.setText(get_msg("target_deck_label", lang))
        self.target_combo.setItemText(0, get_msg("target_anki", lang))
        self.target_combo.setItemText(1, get_msg("target_root", lang))
        self.new_deck_label.setText(get_msg("new_deck_label", lang))
        self.pos_combo.setItemText(0, get_msg("pos_anki", lang))
        self.pos_combo.setItemText(1, get_msg("pos_top", lang))
        self.pos_combo.setItemText(2, get_msg("pos_bottom", lang))
        self.btn_save.setText(get_msg("save", lang))
        self.btn_help.setText(get_msg("help_btn", lang))
        
        self.btn_top.setText(get_msg("move_top", lang))
        self.btn_up.setText(get_msg("move_up", lang))
        self.btn_down.setText(get_msg("move_down", lang))
        self.btn_btm.setText(get_msg("move_btm", lang))
        self.btn_steps.setText(get_msg("dialog_move_steps", lang))
        self.btn_parent.setText(get_msg("dialog_parent_btn", lang))
        self.btn_unparent.setText(get_msg("unparent_btn", lang))
        self.btn_rename.setText(get_msg("rename_btn", lang))
        self.btn_delete.setText(get_msg("delete_btn", lang))
        self.btn_undo.setText(get_msg("undo_btn", lang))
        self.btn_redo.setText(get_msg("redo_btn", lang))
        self.tree_search.setPlaceholderText(get_msg("tree_search_placeholder", lang))

    def show_tutorial(self):
        lang = self.lang_combo.currentData()
        QMessageBox.information(self, get_msg("tutorial_title", lang), get_msg("tutorial_text", lang))


    # ── Undo / Redo helpers ────────────────────────────────────────────────

    def _snapshot_tree(self):
        # 把目前樹狀結構序列化為可還原的 list-of-dict
        result = []
        def walk(qt_item, parent_path):
            for i in range(qt_item.childCount()):
                c = qt_item.child(i)
                did  = c.data(0, Qt.ItemDataRole.UserRole)
                name = c.text(0)
                path = f"{parent_path}::{name}" if parent_path else name
                result.append({'did': did, 'name': name, 'path': path,
                                'parent_path': parent_path, 'expanded': c.isExpanded()})
                walk(c, path)
        walk(self.tree.invisibleRootItem(), "")
        return result

    def _restore_snapshot(self, snapshot):
        # 根據 snapshot 重建樹，保持原有展開狀態與選取
        selected_did = None
        cur = self.tree.currentItem()
        if cur:
            selected_did = cur.data(0, Qt.ItemDataRole.UserRole)

        self.tree.clear()
        nodes = {}   # path -> QTreeWidgetItem
        for entry in snapshot:
            pp = entry['parent_path']
            parent = nodes.get(pp, self.tree.invisibleRootItem())
            item = QTreeWidgetItem(parent)
            item.setText(0, entry['name'])
            item.setData(0, Qt.ItemDataRole.UserRole, entry['did'])
            item.setExpanded(entry['expanded'])
            nodes[entry['path']] = item
            if entry['did'] == selected_did:
                self.tree.setCurrentItem(item)

    def _push_undo(self):
        # 在執行任何變動前呼叫，把當前狀態推入 undo stack，清空 redo stack
        self._undo_stack.append(self._snapshot_tree())
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_redo.setEnabled(bool(self._redo_stack))

    def _on_drag_started(self):
        # 拖曳開始前存快照，供 drop 完成後推入 undo stack
        self._pre_drop_snapshot = self._snapshot_tree()

    def _on_drop_performed(self):
        # 拖曳放下後：把放下前的快照推入 undo stack
        if hasattr(self, '_pre_drop_snapshot') and self._pre_drop_snapshot is not None:
            self._undo_stack.append(self._pre_drop_snapshot)
            self._pre_drop_snapshot = None
            self._redo_stack.clear()
            self._update_undo_redo_buttons()

    def undo(self):
        if not self._undo_stack: return
        self._redo_stack.append(self._snapshot_tree())
        snap = self._undo_stack.pop()
        self._restore_snapshot(snap)
        self._update_undo_redo_buttons()

    def redo(self):
        if not self._redo_stack: return
        self._undo_stack.append(self._snapshot_tree())
        snap = self._redo_stack.pop()
        self._restore_snapshot(snap)
        self._update_undo_redo_buttons()

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
        # 重設搜尋欄
        if hasattr(self, 'tree_search'):
            self.tree_search.blockSignals(True)
            self.tree_search.clear()
            self.tree_search.blockSignals(False)
        # 預設選取第一個項目
        first = self.tree.invisibleRootItem().child(0)
        if first:
            self.tree.setCurrentItem(first)

    def filter_tree(self, text):
        text = text.strip().lower()

        def match_and_show(item):
            name = item.text(0).lower()
            self_match = (text in name) if text else True
            child_match = False
            for i in range(item.childCount()):
                if match_and_show(item.child(i)):
                    child_match = True
            visible = self_match or child_match
            item.setHidden(not visible)
            if visible:
                item.setExpanded(True)
            return visible

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            match_and_show(root.child(i))

    def change_parent_of_item(self):
        item = self.tree.currentItem()
        lang = self.lang_combo.currentData()
        if not item:
            QMessageBox.warning(self, "Warning", get_msg("dialog_no_selection", lang))
            return

        root_name = get_msg("dialog_parent_root", lang)
        valid_targets = [(f"🌟 {root_name}", "")]

        def is_descendant(potential_descendant, ancestor):
            p = potential_descendant.parent()
            while p:
                if p == ancestor: return True
                p = p.parent()
            return False

        def get_paths(p, current_path):
            for i in range(p.childCount()):
                c = p.child(i)
                if c == item or is_descendant(c, item): continue
                name = c.text(0)
                full_path = f"{current_path}::{name}" if current_path else name
                valid_targets.append((full_path, c))
                get_paths(c, full_path)

        get_paths(self.tree.invisibleRootItem(), "")

        title = get_msg("dialog_parent_title", lang)
        desc = get_msg("dialog_parent_desc", lang)
        placeholder = get_msg("search_placeholder", lang)
        
        dialog = SearchableDeckDialog(self, title, desc, valid_targets, placeholder)
        if dialog.exec():
            target_data = dialog.get_selected_data()
            if target_data is None: return
            
            if target_data == "":
                target_item = None
            else:
                target_item = target_data

            self._push_undo()
            old_parent = item.parent() or self.tree.invisibleRootItem()
            old_parent.takeChild(old_parent.indexOfChild(item))
            
            new_parent = target_item if target_item else self.tree.invisibleRootItem()
            new_parent.addChild(item)
            if target_item: target_item.setExpanded(True)
            self.tree.setCurrentItem(item)


    def unparent_item_in_tree(self):
        # 將選取的牌組在樹狀圖中往上移出 N 層母牌組
        item = self.tree.currentItem()
        lang = self.lang_combo.currentData()
        if not item:
            QMessageBox.warning(self, "Warning", get_msg("dialog_no_selection", lang))
            return

        # 計算目前深度（往上找幾個 parent）
        depth = 0
        p = item.parent()
        while p:
            depth += 1
            p = p.parent()

        if depth == 0:
            QMessageBox.warning(self, "Warning", get_msg("warn_already_root", lang))
            return

        title = get_msg("unparent_prompt_title", lang)
        desc = get_msg("unparent_prompt_desc", lang)
        levels, ok = QInputDialog.getInt(self, title, desc, 1, 1, depth, 1)
        if not ok: return

        if levels > depth:
            QMessageBox.warning(self, "Warning", get_msg("warn_unparent_exceed", lang, depth=depth))
            return

        # 找到目標祖先（往上移 levels 層後的父節點）
        ancestor = item.parent()
        for _ in range(levels - 1):
            ancestor = ancestor.parent()

        # ancestor 的父就是我們要插入的新父層
        new_parent = ancestor.parent() if ancestor.parent() else self.tree.invisibleRootItem()

        # 從舊父節點取出 item
        self._push_undo()
        old_parent = item.parent()
        old_parent.takeChild(old_parent.indexOfChild(item))

        # 插入到 ancestor 的後面
        ins_idx = new_parent.indexOfChild(ancestor) + 1
        new_parent.insertChild(ins_idx, item)
        self.tree.setCurrentItem(item)


    def rename_item_in_tree(self):
        item = self.tree.currentItem()
        lang = self.lang_combo.currentData()
        if not item:
            QMessageBox.warning(self, "Warning", get_msg("dialog_no_selection", lang))
            return
        old_name = item.text(0)
        title = get_msg("rename_title", lang)
        desc  = get_msg("rename_desc", lang)
        new_name, ok = QInputDialog.getText(self, title, desc, text=old_name)
        if not ok: return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Warning", get_msg("rename_empty", lang))
            return
        if '::' in new_name:
            QMessageBox.warning(self, "Warning", get_msg("rename_has_sep", lang))
            return
        if new_name == old_name: return
        self._push_undo()
        item.setText(0, new_name)

    def delete_item_in_tree(self):
        item = self.tree.currentItem()
        lang = self.lang_combo.currentData()
        if not item:
            QMessageBox.warning(self, "Warning", get_msg("dialog_no_selection", lang))
            return
        name = item.text(0)
        title = get_msg("delete_confirm_title", lang)
        desc  = get_msg("delete_confirm_desc", lang, name=name)
        reply = QMessageBox.question(self, title, desc,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        self._push_undo()
        parent = item.parent() or self.tree.invisibleRootItem()
        parent.takeChild(parent.indexOfChild(item))

    def move_item_in_tree(self, direction):
        item = self.tree.currentItem()
        lang = self.lang_combo.currentData()
        if not item:
            QMessageBox.warning(self, "Warning", get_msg("dialog_no_selection", lang))
            return

        parent = item.parent() or self.tree.invisibleRootItem()
        idx = parent.indexOfChild(item)
        count = parent.childCount()
        new_idx = idx

        if direction == "up":
            if idx > 0: new_idx = idx - 1
            else: QMessageBox.information(self, "Info", get_msg("warn_cannot_move", lang))
        elif direction == "down":
            if idx < count - 1: new_idx = idx + 1
            else: QMessageBox.information(self, "Info", get_msg("warn_cannot_move", lang))
        elif direction == "top":
            if idx == 0: QMessageBox.information(self, "Info", get_msg("warn_cannot_move", lang))
            else: new_idx = 0
        elif direction == "btm":
            if idx == count - 1: QMessageBox.information(self, "Info", get_msg("warn_cannot_move", lang))
            else: new_idx = count - 1
        elif direction == "steps":
            title = get_msg("dialog_move_prompt_title", lang)
            desc = get_msg("dialog_move_prompt_desc", lang)
            steps, ok = QInputDialog.getInt(self, title, desc, 0, -999, 999, 1)
            if ok and steps != 0:
                intended_idx = idx + steps
                if intended_idx < 0 or intended_idx >= count:
                    QMessageBox.warning(self, "Warning", get_msg("warn_out_of_bounds", lang, max_idx=count-1))
                else: new_idx = intended_idx

        if new_idx != idx:
            self._push_undo()
            parent.takeChild(idx)
            parent.insertChild(new_idx, item)
            self.tree.setCurrentItem(item)

    def save(self):
        final_lang = self.lang_combo.currentData()
        new_conf = {CONF_KEY_LANG: final_lang, CONF_KEY_TARGET_DECK: self.target_combo.currentData(), CONF_KEY_POS: self.pos_combo.currentData()}
        mw.addonManager.writeConfig(__name__, new_conf)

        global _tools_action
        if _tools_action is not None:
            _tools_action.setText(get_msg("adv_mgr", final_lang))

        # Collect IDs and new paths from tree
        ids = []
        forced_paths = {}
        def traverse(p, current_path):
            for i in range(p.childCount()):
                c = p.child(i)
                did = c.data(0, Qt.ItemDataRole.UserRole)
                ids.append(did)
                basename = c.text(0)
                full_path = f"{current_path}::{basename}" if current_path else basename
                forced_paths[did] = full_path
                traverse(c, full_path)

        traverse(self.tree.invisibleRootItem(), "")

        # Delete decks that were removed from the tree
        all_ids_in_db = {d.id for d in mw.col.decks.all_names_and_ids() if d.id != 1}
        ids_in_tree   = set(ids)
        ids_to_delete = all_ids_in_db - ids_in_tree
        if ids_to_delete:
            mw.checkpoint("Delete Decks")
            mw.col.modSchema(check=False)
            for did in ids_to_delete:
                mw.col.decks.remove([did])
            mw.col.decks.save()

        apply_order_ultimate(ids, forced_paths)
        tooltip(get_msg("success", final_lang)); self.accept()

def on_deck_menu(menu, did):
    if did == 1: return

    # 計算該牌組在同層的位置
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
            if parent_node: parent_node['children'].append(node)
            else: root_nodes.append(node)
        else: root_nodes.append(node)

    siblings = root_nodes
    if did in node_map:
        parts = node_map[did]['c_name'].split('::')
        if len(parts) > 1:
            parent_path = '::'.join(parts[:-1])
            parent_node = next((n for n in node_map.values() if n['c_name'] == parent_path), None)
            if parent_node: siblings = parent_node['children']
    idx = next((i for i, s in enumerate(siblings) if s['id'] == did), 0)
    count = len(siblings)
    at_top = (idx == 0)
    at_btm = (idx == count - 1)

    sub = menu.addMenu(get_msg("menu_name"))
    act_top = sub.addAction(get_msg("move_top")); act_top.triggered.connect(lambda: quick_move(did, "top"))
    act_up  = sub.addAction(get_msg("move_up"));  act_up.triggered.connect(lambda: quick_move(did, "up"))
    act_dn  = sub.addAction(get_msg("move_down")); act_dn.triggered.connect(lambda: quick_move(did, "down"))
    act_btm = sub.addAction(get_msg("move_btm")); act_btm.triggered.connect(lambda: quick_move(did, "btm"))
    if at_top:  act_top.setEnabled(False); act_up.setEnabled(False)
    if at_btm:  act_btm.setEnabled(False); act_dn.setEnabled(False)
    sub.addAction(get_msg("move_steps_menu")).triggered.connect(lambda: quick_move_steps(did))
    sub.addSeparator()
    sub.addAction(get_msg("move_parent")).triggered.connect(lambda: quick_change_parent(did))

    # 移出母牌組：已在最上層則 disable
    target_info = next((d for d in all_d if d.id == did), None)
    act_unparent = sub.addAction(get_msg("unparent_menu"))
    act_unparent.triggered.connect(lambda: quick_unparent(did))
    if target_info and clean_name(target_info.name).count('::') == 0:
        act_unparent.setEnabled(False)

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

# MANIFEST 更新至 v4.4.0
MANIFEST = {
    "package": "UltimateDeckReorderPlus",
    "name": "Deck_Reorder (v4.4.0)",
    "mod": 1710850031
}

DEFAULT_CONFIG = {
    "reorder_lang": "en",
    "new_deck_pos": "anki",
    "auto_target_deck": "anki"
}

def build_addon():
    filename = 'Deck_Reorder.ankiaddon'
    with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('__init__.py', ADDON_CODE.strip())
        zf.writestr('manifest.json', json.dumps(MANIFEST, indent=4, ensure_ascii=False))
        meta_data = {"name": MANIFEST["name"], "mod": MANIFEST["mod"]}
        zf.writestr('meta.json', json.dumps(meta_data, indent=4, ensure_ascii=False))
        zf.writestr('config.json', json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False))
    print(f"Build Successful (v4.4.0): {os.path.abspath(filename)}")

if __name__ == "__main__":
    build_addon()
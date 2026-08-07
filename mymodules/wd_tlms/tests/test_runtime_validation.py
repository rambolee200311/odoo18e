# -*- coding: utf-8 -*-
"""
运行时集成测试——捕获静态门禁无法发现的运行时报错。

覆盖类型：
  - view_mode="tree" 问题（Odoo 18 tree→list）
  - menuitem parent XML ID 缺失/后置
  - act_window 引用的 res_model 缺少匹配视图
  - act_window 的 view_refs 指向不存在的视图

运行方式：
  odoo-bin -u wd_tlms --test-enable --stop-after-init

执行入口：
  execution/scripts/test_runner.py
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestRuntimeValidation(TransactionCase):
    """运行时验证——静态扫描无法捕获的集成问题"""

    def _module_actions(self):
        """获取 wd_tlms 模块定义的所有 act_window"""
        IrModelData = self.env['ir.model.data']
        xmlids = IrModelData.search([
            ('model', '=', 'ir.actions.act_window'),
            ('module', '=', 'wd_tlms'),
        ])
        return self.env['ir.actions.act_window'].browse(xmlids.mapped('res_id'))

    def _module_menus(self):
        """获取 wd_tlms 模块定义的所有菜单"""
        IrModelData = self.env['ir.model.data']
        xmlids = IrModelData.search([
            ('model', '=', 'ir.ui.menu'),
            ('module', '=', 'wd_tlms'),
        ])
        return self.env['ir.ui.menu'].browse(xmlids.mapped('res_id'))

    def _module_views(self):
        """获取 wd_tlms 模块定义的所有视图"""
        IrModelData = self.env['ir.model.data']
        xmlids = IrModelData.search([
            ('model', '=', 'ir.ui.view'),
            ('module', '=', 'wd_tlms'),
        ])
        return self.env['ir.ui.view'].browse(xmlids.mapped('res_id'))

    # -----------------------------------------------------------
    # Test 1: Odoo 18 view_mode 兼容性
    # -----------------------------------------------------------
    def test_01_view_mode_no_tree(self):
        """所有 act_window 的 view_mode 不能含 'tree'（Odoo 18 应使用 'list'）"""
        bad = self._module_actions().filtered(
            lambda a: 'tree' in (a.view_mode or '').split(',')
        )
        if bad:
            details = '\n'.join(
                f'  {a.name:40s} model={a.res_model:30s} view_mode={a.view_mode}'
                for a in bad
            )
            self.fail(
                f'Found {len(bad)} act_window(s) with "tree" in view_mode '
                f'(Odoo 18: use "list" instead):\n{details}'
            )

    # -----------------------------------------------------------
    # Test 2: Menuitem parent 存在性
    # -----------------------------------------------------------
    def test_02_menuitem_parent_exists(self):
        """所有模块菜单的 parent 必须指向存在的菜单"""
        menus = self._module_menus()
        bad = menus.filtered(
            lambda m: m.parent_id and m.parent_id not in menus
        )
        if bad:
            details = '\n'.join(
                f'  {m.name:40s} parent={m.parent_id.display_name}'
                f' (id={m.parent_id.id})'
                for m in bad
            )
            self.fail(f'Found {len(bad)} menus whose parent is not in our module:\n{details}')

    # -----------------------------------------------------------
    # Test 3: Action res_model 有对应视图
    # -----------------------------------------------------------
    def test_03_action_res_model_has_view(self):
        """所有 act_window 的每个 view_mode 类型，其 res_model 必须至少有一个对应视图"""
        actions = self._module_actions()
        bad_actions = self.env['ir.actions.act_window']
        for action in actions:
            modes = [m.strip() for m in (action.view_mode or '').split(',') if m.strip()]
            for mode in modes:
                # Odoo 18: list = tree (backward compat during migration)
                if mode == 'list':
                    mode = ['list', 'tree']
                else:
                    mode = [mode]
                has_view = bool(self.env['ir.ui.view'].search_count([
                    ('model', '=', action.res_model),
                    ('type', 'in', mode),
                ]))
                if not has_view:
                    bad_actions |= action
                    break

        if bad_actions:
            details = '\n'.join(
                f'  {a.name:40s} model={a.res_model:30s} view_mode={a.view_mode}'
                for a in bad_actions
            )
            self.fail(
                f'Found {len(bad_actions)} act_window(s) referencing views '
                f'that do not exist for their model:\n{details}'
            )

    # -----------------------------------------------------------
    # Test 4: View ref 存在性
    # -----------------------------------------------------------
    def test_04_action_view_refs_exist(self):
        """act_window 的 view_ids 引用的视图必须真实存在"""
        actions = self._module_actions()
        errors = []
        for action in actions:
            for view_ref in action.view_ids:
                if view_ref.view_id and not view_ref.view_id.exists():
                    errors.append(
                        f'{action.name} view_ids ref: view_id={view_ref.view_id.id} '
                        f'does not exist (mode={view_ref.view_mode})'
                    )
        if errors:
            self.fail('View ref errors:\n' + '\n'.join(f'  {e}' for e in errors))

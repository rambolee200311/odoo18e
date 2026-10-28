# 荷兰保税仓 WMS — 三阶段实施路线图

## Phase 1 — 基础骨架（当前，修改补充）

现有代码已有较好的基础（bonded.book、bonded.stock、bonded.inbound/outbound、bonded.customs.file、bonded.verification、bonded.value.limit），但与文档对照还有 6 个关键缺口。

### 1. 扩展：bonded.inbound / bonded.outbound 状态机

现有 `bonded.inbound` 和 `bonded.outbound` 本身就是预报单 + 指令的合一体，不是 Odoo 原生 stock.picking。无需新建模型，只需扩展状态。

**状态机扩展：**

```
当前: draft → confirmed → in_progress → done → cancelled
扩展: draft → confirmed → declared → released → in_progress → done → cancelled
         新增: declared (已申报)   released (已放行)
```

**动作映射：**

| 状态 | 触发条件 | 系统动作 |
|---|---|---|
| confirmed → declared | 关联 customs_file 提交 | 更新指令状态 |
| declared → released | 海关放行 | 允许创建 stock.picking |
| released → in_progress | 创建 stock.picking | 原 confirmed → in_progress 逻辑 |
| in_progress → done | stock.picking 完成 | 原逻辑（创建 bonded.stock + book.line）|

**流程改造（customs_file 联动）：**

```
当前: customs_file approved → 直接创建 bonded.inbound (confirmed)
改为: customs_file submitted → bonded.inbound (declared)
      customs_file approved → bonded.inbound (released)
      用户确认 → bonded.inbound (in_progress)
```

**为什么必须加：** 文档里的预报单承担了"客户发起→关务申报→海关放行→仓库执行"的中间状态衔接。当前代码直接跳过了客户确认和额度占用的环节。

### 2. 新增：台账明细行 bonded.book.line

文档第五节**核心**——那张海关监管状态表格就是台账行的数据模型。

**新建模型字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| date | Date | 日期 |
| operation_type | Selection | 保税入库/清关出库/T1过境出库/抽样检查/盘亏处置/RTO退运/销毁处置/库存快照 |
| product_id | Many2one | 商品 |
| qty_change | Float | 本次变动数量 (+/-) |
| from_status | Selection | 变动前海关监管状态 |
| to_status | Selection | 变动后海关监管状态 |
| direction | Selection | In/Out/无 |
| ref_doc_no | Char | 关联单号 |
| inbound_tracking_no | Char | 入库跟踪号（贯穿全局的关键字段） |
| customer_batch_no | Char | 客户批次号 |
| running_balance_qty | Float | 当前结存数量（按跟踪号） |
| bonded_stock_id | Many2one | 关联 bonded.stock |
| customs_file_id | Many2one | 关联海关申报单 |
| picking_id | Many2one | 关联仓库单据 |

**修改 `bonded.book`：** 加 `line_ids` (One2many)

### 3. 新增：入库跟踪号 + 客户批次号

文档里这两个字段是台账的命脉。入库必录跟踪号，出库必选对应跟踪号。

- `bonded.stock` → 加 `inbound_tracking_no` (char, required), `customer_batch_no` (char)
- `bonded.inbound.line` → 加 `inbound_tracking_no`, `customer_batch_no`
- `bonded.outbound.line` → 加 `inbound_tracking_no`（选择要扣减的库存跟踪号）

### 4. EORI 与海关资质管控

当前 `bonded.customs.file` 的 EORI 字段是纯文本，无校验、无格式检查、和 partner 无关。这是 Phase 1 就必须做的硬管控。

**`res.partner` 扩展：**

- `eori_number` (char, 格式: NL+9位数字/其他EU格式)
- `eori_valid_until` (date)
- `vat_number` (char)
- `customs_auth_ids` (One2many → bonded.customs.authorization)

**`res.company` 扩展：**

- `eori_number`
- `warehouse_license_no`（保税仓授权号，如 C510）
- `warehouse_license_expiry`

**新建模型 `bonded.customs.authorization`：**

- `auth_type`（EORI / C510 / Article 23 VAT deferment 等）
- `auth_no`、`valid_from` / `valid_until`、`partner_id`

**校验逻辑：** `customs_file submit` 时校验 declarant/consignor/consignee 的 EORI 格式 + 有效期。

### 5. 5 本台账视图

现有视图只有 `bonded.book` header，没有台账明细视图。

**新增视图：**

1. 保税货物入出库台账视图 ← tree view on `bonded.book.line`
2. 货值/额度台账视图 ← tree view on `bonded.value.limit` + 汇总
3. 海关申报放行台账视图 ← tree view on `bonded.customs.file`
4. 转关/MRN监管台账视图 ← tree view on `bonded.customs.file` (filter T1 types) + MRN tracking
5. 核销处置台账视图 ← tree view on `bonded.verification`

每个台账加专门的菜单入口。

### 6. 台账自动生成逻辑

当前 `_action_done()` 只创建 bonded.stock + verification，不写台账行。

- `bonded.inbound._action_done()` → 完成后自动创建 `bonded.book.line`（入库行）
- `bonded.outbound._action_done()` → 完成后自动创建 `bonded.book.line`（出库行）
- `bonded.verification` 复核通过 → 创建 `bonded.book.line`（核销处置行）
- snapshot 生成 → 创建 `bonded.book.line`（快照行，变动数量=0）

### Phase 1 修改清单

| 改动类型 | 文件 | 改动内容 |
|---|---|---|
| **修改** | `models/bonded_inbound.py` | 扩展状态机(加 declared/released)、台账自动生成 |
| **修改** | `models/bonded_outbound.py` | 扩展状态机(加 declared/released)、台账自动生成 |
| **新增模型** | `models/bonded_book_line.py` | 台账明细行 + 实时结存逻辑 |
| **新增模型** | `models/bonded_customs_authorization.py` | 海关授权码管理 |
| **修改** | `models/bonded_book.py` | 加 line_ids、额度合计 |
| **修改** | `models/bonded_stock.py` | 加 inbound_tracking_no、customer_batch_no |
| **修改** | `models/bonded_customs_file.py` | EORI 校验 + 状态联动调整 |
| **修改** | `models/bonded_verification.py` | 复核通过后自动写台账行 |
| **修改** | `models/inherited_models.py` | res.partner EORI 扩展 |
| **新增视图** | `views/bonded_book_line_views.xml` | 台账明细行视图 |
| **修改** | `views/bonded_menus.xml` | 5台账菜单 |

---

## Phase 2 — 运营闭环

### 2.1 仓储计费自动化

现有 `bonded.charge.item`、`bonded.charge.unit` 和 `bonded.charge.line` 已提供保税计费基础数据与费用明细，计费仍为手动分配。

**新建模型：**

- `bonded.charge.rule` — 计费规则引擎
- 关联 bonded.book、客户(project)、产品分类
- 计费类型: storage / handling_in / handling_out / customs_declaration / t1_transit / monthly_fixed
- 计价单位: per_piece / per_pallet / per_shipment / per_mrn / per_day / per_month
- 单价金额、币别、生效/失效日期

- `bonded.charge.run` — 计费跑批
- 仓储费：每天/每月跑批，计算每票货物在仓天数 × 单价
- 操作费：入库/出库完成时自动生成
- 报关费：customs_file submit 时自动生成
- 结果写入 `bonded.charge.line`

**自动触发点：**

- inbound done → 开始计仓储费，生成操作费
- outbound done → 停止计仓储费，生成操作费
- customs_file submitted → 生成报关费
- 每月1日 cron → 生成月度固定费和仓储费账单

### 2.2 库存异常完整流程

**盘点流程：**

- `bonded.stocktaking.order` — 盘点单
- 盘点范围: 按库位/产品/客户/批次
- 自动生成盘点清单（当前账面库存）
- 盘点人、复核人
- `bonded.stocktaking.line` — 盘点明细
- product, location, lot, 账面数量, 实盘数量, 差异
- 差异类型: 盘盈/盘亏/一致
- 差异审批流: 仓库提交 → 关务复核 → 差异确认
- 盘亏 → 创建 `bonded.verification` (write_off_type=shortage)
- 盘盈 → 调整库存
- 审批后自动写 `bonded.book.line`

**销毁流程：**

- `bonded.destruction.request` — 销毁申请
- 原因、涉及货物 (bonded.stock)、数量
- 凭证上传（照片、称重证明）
- 状态: draft → customs_submitted → customs_approved → executed → done
- 海关批复号记录
- 执行后自动: 更新 bonded.stock 状态为 destroyed → 创建 verification → 写 book.line

**RTO 退运流程：**

- `bonded.rto.request` — 退运申请
- 原入库跟踪号（必选）、退运原因、目的国
- 海关审批跟踪
- 执行后: bonded.stock 状态 → rto → verification → book.line

**简单加工记录：**

- `bonded.processing.order` — 加工单
- 投入货物 (bonded.stock)、加工作业类型（贴标/分拣/包装）
- 产出的新 bonded.stock（不改变 HS 编码、原产地）
- 关联出库预报单（加工后出库场景）

### 2.3 客户自助门户

通过 record rules + portal 视图实现，不需要新建模型：

- 客户专属仪表盘：只看自己的库存结存
- 在线提交预报单：客户提交 → 创建 draft 预报警
- 单证下载：客户可下载自己的报关单、核销凭证

**权限：**

- 新增客户门户用户组
- portal record rules: 只读自己的 bonded.stock / bonded.book.line / bonded.customs.file

### 2.4 预警与通知

**新建模型：**

- `bonded.alert.rule` — 预警规则配置
- `bonded.alert.log` — 预警触发记录

**预警类型：**

| 预警 | 触发逻辑 | 实现方式 |
|---|---|---|
| T1 deadline 预警 | 每日 cron 扫描 transit_deadline | `customs_file.transit_deadline` - 48h |
| 额度预警 | 每笔 customs_file submit 时检查 | `value.limit` available_value < 20% |
| 账册到期 | 每日 cron | `bonded.book.valid_until` - 30d |
| 盘点到期 | 每日 cron 检查盘点周期 | `stocktaking.order` 上次完成日期 |
| EORI 到期 | 每日 cron | `res.partner.eori_valid_until` - 30d |
| 仓储费月结 | 每月1日 cron | 自动汇总生成费用行 |

### 2.5 担保管理 Guarantee Management

**新建模型：**

- `bonded.guarantee` — 担保单
- guarantee_type: bank_guarantee / cash_deposit / parent_company_guarantee
- 担保编号、银行/机构
- 担保金额、币别 (EUR)
- 生效日期、失效日期
- 关联 bonded.book、关联 res.partner
- 状态: active / expired / released

- `bonded.guarantee.transaction` — 担保使用记录
- 每次入库/出库时登记担保占用/释放
- 当前已用额度、可用额度

**联动逻辑：**

- 入库确认时：占用担保额度
- 出库完成时：释放担保额度
- 担保到期前 30 天：预警通知
- 担保不足时：阻止入库确认（与 value.limit 联动）

### 2.6 月报与合规报告增强

- `bonded.monthly.report` 完善生成逻辑（从 bonded.book.line 按月汇总）
- 海关标准月报格式导出（PDF / CSV）
- Intrastat 数据提取

### 2.7 海关门户 Customs Portal

给荷兰海关工作人员（或海关检查时）用的专用只读视图。文档里 5 本台账的查看权限都包含"海关工作人员"。

**实现方式：**

- 新建菜单组"海关门户"，与内部运营菜单分开
- 所有视图：只读，不可增删改
- 展示 5 本台账的专门列表界面，按日期范围/商品/客户/监管状态快速筛选
- 每本台账支持导出为标准格式（CSV / PDF）
- 海关申报放行台账：海关可直接看到所有申报的提交时间、放行时间、操作人
- MRN 监管台账：海关可查看 T1 在途状态、起运地/目的地、核销进度

**权限：**

- 新建用户组 "海关人员 Customs Officer"
- 仅授予只读权限，无任何写权限
- 所有 `bonded.*` 模型对海关人员开放只读

**注意：** Phase 1 的 5 台账视图是海关门户的基础。Phase 2 海关门户 = Phase 1 视图 + 海关专用入口 + 导出 + 权限隔离。

---

## Phase 3 — 系统集成

### 3.1 NCTS T1 集成

直接和欧盟 NCTS 系统对话，实现 T1 全流程自动化。

**新建模型：**

- `ncts.endpoint` — NCTS 网关配置
- 环境: test / production
- 网关 URL、端口、证书
- 运营商 EORI

- `ncts.message` — 消息收发记录
- message_type: IE015 / IE003 / IE013 / IE014 / IE018 / IE025 / IE044
- direction: outbound / inbound
- xml_content（原文）
- parsed_fields: MRN, status, error_code, timestamp
- 关联 bonded.customs.file

- `ncts.certificate` — 数字证书管理
- 证书文件、有效期、颁发机构
- 到期预警

**自动收发流程：**

| 场景 | 消息 | 系统动作 |
|---|---|---|
| T1 出库申报 | 发送 IE015 → 接收 IE003 (MRN回执) | 自动填写 customs_file.mrn |
| 作为目的地接收 T1 | 发送 IE014 (到达通知) | 自动更新 pre_mrn 状态为 arrived |
| 目的地海关确认 | 接收 IE025 (T1闭环) | 自动更新 pre_mrn 为 closed，触发入库 |
| 海关查验通知 | 接收 IE013 | 自动创建预警，更新 book.line 状态 |
| T1 过期/异常 | 接收 IE044 (监管结果) | 自动触发异常预警 |

### 3.2 EU Trader Portal / DMS 对接

从关务手工录入 -> 系统自动提交 B3 申报。

**新建模型：**

- `dms.config` — DMS 配置
- 环境、API 端点、认证方式

- `dms.declaration.submission` — 申报提交记录
- XML 原文、海关回执、状态
- 关联 bonded.customs.file

**功能：**

- 生成 SAD C88 XML（从 bonded.customs.file + line_ids 转换）
- 自动提交 B3 入库/出库申报
- 接收回执：放行/退单/查验
- 申报状态自动同步（无需手动点 action_approve / action_reject）

### 3.3 高级分析与审计

**审计模式（一键导出）：**

- 5 本台账 CSV（按日期范围）
- 所有出入库单 PDF
- 所有海关申报单 SAD XML
- 盘点报告
- 核销记录
- 操作日志 (bonded.log 按时间线导出)

**分析报表：**

- 客户维度：各客户库存周转、费用汇总、申报统计
- 商品维度：HS 编码分布、流转分析
- 监管状态维度：Entrepot / Vrij / IVV 分布变化趋势
- 时效分析：T1 平均闭环时间、申报到放行平均时间

**数据留存：** bonded.log 自动归档（7 年）

---

## 三阶段总览

```
Phase 1 (当前)          Phase 2 (运营)          Phase 3 (集成)
───────────────        ───────────────         ───────────────
 状态机扩展              计费自动化               NCTS T1 对接
台账明细行              盘点/销毁/RTO流程        DMS 自动申报
EORI 资质管控           客户自助门户             高级审计
5台账视图               预警通知系统              分析报表
流程串联+台账自动生成     担保管理
月报合规增强
海关门户
```

---

*最后更新: 2026-07-06*
*依据文档: 荷兰保税仓需求规范（含 5 本核心台账、业务流程、海关监管状态）*

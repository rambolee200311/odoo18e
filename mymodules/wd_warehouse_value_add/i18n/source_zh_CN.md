# Warehouse Value Add Chinese Source Text Inventory

The user interface and module metadata use English source text. This inventory preserves the original Chinese text for the translation file to be provided later. It is reference material only and is not an Odoo translation file.

## Dashboard

| English source text | Original Chinese text |
| --- | --- |
| Warehouse Value-Added Operations | 库内增值作业 |
| Select an entry point | 请选择工作入口 |
| PDA Work Order Entry | PDA 作业录入 |
| On-site entry, scanning, photos, and work order submission | 现场录入、扫码、拍照、提交作业单 |
| Work Order Management | 作业单管理 |
| Search, filter, view, and manage existing work orders | 查询、筛选、查看和管理已有作业单 |

## PDA Work Order

| English source text | Original Chinese text |
| --- | --- |
| Warehouse Value-Added Work Order | 库内增值作业单 |
| New Work Order | 新建作业单 |
| Basic Information (Read-Only) | 基础信息（只读） |
| Work Order Number | 作业单号 |
| Created On | 新增时间 |
| Generated after saving | 保存后生成 |
| Related Document | 单据信息 |
| Document Type | 关联对象 |
| Inbound Order | 入库订单 |
| Outbound Order | 出库订单 |
| Transfer Order | 调拨订单 |
| Related Document Number | 关联单据号 |
| Enter or scan a document number | 请输入或扫描单据号 |
| Scan | 扫码 |
| Customer (Auto-filled) | 客户（自动带出） |
| Auto-filled after resolving the document | 解析订单后自动带出 |
| Operator (Current User) | 操作员（当前登录） |
| Resolved | 已解析： |
| ✓ Resolved: | ✓ 已解析： |
| Operation Lines (At Least 1) | 作业明细（至少 1 条） |
| + Add Operation Line | + 添加作业行 |
| Add Operation Line | 新增作业明细 |
| No operation lines. Add an operation line to continue. | 暂无作业明细，请添加作业行 |
| Operation Line | 作业明细 |
| Save | 保存 |
| Cancel | 取消 |
| Delete | 删除 |
| Operation Type | 操作类型 |
| Operation Type: | 操作类型： |
| Select an operation type | 请选择作业类型 |
| Quantity / Time | 数量/工时 |
| Quantity / Time: | 数量/工时： |
| Unit | 单位 |
| Unit: | 单位： |
| Automatic | 自动 |
| Notes | 备注 |
| Notes: | 备注： |
| Work Evidence Attachments | 作业凭证附件 |
| 📷 Take Photo | 📷 拍照 |
| 🗂 Select Multiple from Gallery | 🗂 从相册多选 |
| New | 新增 |
| Save Draft | 保存草稿 |
| Submit | 提交 |
| Read-Only | 只读 |
| ① Operation Type | ① 操作类型 |
| Select from the list. Barcode scanning is not supported in this version. | 第一版仅下拉选择，暂不支持扫码 |
| ② Quantity / Time | ② 数量/工时 |
| Enter quantity for physical work or time for manual work, based on the operation type. | 实物作业填数量，人工作业填工时，由操作类型决定 |
| ③ Notes (Optional) | ③ 备注（选填） |
| Notes (Optional) | 备注（选填） |
| Optional: record exceptions or special work instructions. | 记录异常情况、特殊作业说明，可不填 |
| Confirm Add | 确认添加 |
| Cancel Work Order | 作废作业单 |
| Cancellation Reason | 作废原因 |
| Enter a cancellation reason | 请输入作废原因 |
| Confirm Cancellation | 确认作废 |

## Status and Notifications

| English source text | Original Chinese text |
| --- | --- |
| Draft | 草稿 |
| Submitted | 已提交 |
| Cancelled | 已作废 |
| New | 新建 |
| Please select an operation type. | 请选择作业类型。 |
| Please enter and resolve the related document number first. | 请先输入并解析关联单据号。 |
| Please enter a cancellation reason. | 请输入作废原因。 |
| Work order cancelled. | 作业单已作废。 |
| Cancellation failed. | 作废失败。 |

## Module Metadata

| English source text | Original Chinese text |
| --- | --- |
| Register warehouse value-added operations such as labeling and wrapping through Web and PDA. | 仓库贴标、缠膜等库内增值作业登记，支持 Web 电脑端和 PDA 手持端录单 |

### Original Module Description

```text
仓库库内增值作业登记模块，用于记录贴标、缠膜、换箱、打托、
盘点等现场实际发生的库内增值作业。

业务规则
--------

1. 一张作业单只对应一个操作员。
   不同操作员分别建立自己的作业单。

2. 同一个入库订单、出库订单或其他业务订单，
   可以关联多张库内增值作业单。

3. 一张作业单可以登记一条或多条作业明细，
   支持一单多作业。

4. 作业明细使用统一的“数量/工时”字段。
   系统根据所选操作类型自动带出对应计量单位，
   单位无需仓管人工填写。

5. 关联单据号支持扫码录入或手工输入，
   系统识别并绑定对应业务单据。

6. 图片、视频作为作业凭证，可根据现场情况选择上传，
   为非必填项，并支持多个附件。

7. Web 电脑端用于办公录单和历史单据查询。

8. PDA 手持端用于仓库现场快速录单。
   PDA 操作员默认取当前登录人员并只读展示，
   操作人员登记本人实际完成的作业。

9. 草稿状态允许保存和继续修改。
   草稿允许暂时没有作业明细，
   但提交时必须至少存在一条有效作业明细。

10. 单据提交后核心业务字段锁定，
    不允许直接修改；错误数据后续通过更正流程处理。

11. 作业单号、新增时间、提交人、提交时间等系统字段
    均由系统自动维护，人工不可修改。

12. 本模块记录仓库增值作业事实。
    当前版本不包含增值作业计费、结算等财务业务。
```

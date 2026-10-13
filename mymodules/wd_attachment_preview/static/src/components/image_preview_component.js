/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * ImagePreviewComponent - 独立的图片/视频缩略图预览组件
 * 
 * 可在 PDA 前端、自定义 Action 等非表单场景中使用。
 * 不依赖 Odoo 表单字段架构，直接接收附件数组作为 props。
 * 
 * 使用示例:
 *    import { ImagePreviewComponent } from "@wd_attachment_preview/components/image_preview_component";
 *    
 *    // 在组件中注册
 *    static components = { ImagePreviewComponent };
 *    
 *    // 在模板中使用
 *    <ImagePreviewComponent 
 *        attachments="state.attachments"
 *        editable="true"
 *        onRemove.bind="removeAttachment"
 *    />
 * 
 * Props:
 *    - attachments: Array<{id: number, name: string, mimetype?: string}>
 *    - editable: boolean (是否显示删除按钮，默认 false)
 *    - onRemove: (id: number) => void (删除回调)
 */
export class ImagePreviewComponent extends Component {
    static template = "wd_attachment_preview.ImagePreviewComponent";
    
    static props = {
        attachments: { type: Array, optional: true },
        editable: { type: Boolean, optional: true },
        onRemove: { type: Function, optional: true },
    };
    
    static defaultProps = {
        attachments: [],
        editable: false,
    };

    setup() {
        this.state = useState({
            previewId: null,
        });
    }

    /**
     * 获取缩略图 URL
     * 使用 Odoo 的 /web/image 端点，自动按比例缩放
     */
    getThumbnailUrl = (attachmentId) => {
        return `/web/image/${attachmentId}/240x180`;
    }

    /**
     * 获取完整图片/视频 URL
     */
    getContentUrl = (attachmentId) => {
        return `/web/content/${attachmentId}`;
    }

    /**
     * 判断是否为图片
     */
    isImage = (attachment) => {
        if (!attachment) return false;
        var mimetype = attachment.mimetype || '';
        return mimetype.startsWith('image/');
    }

    /**
     * 判断是否为视频
     */
    isVideo = (attachment) => {
        if (!attachment) return false;
        var mimetype = attachment.mimetype || '';
        return mimetype.startsWith('video/');
    }

    /**
     * 获取文件扩展名
     */
    getFileExtension = (attachment) => {
        if (!attachment || !attachment.name) return '';
        var parts = attachment.name.split('.');
        return parts.length > 1 ? parts.pop().toUpperCase() : '';
    }

    /**
     * 打开预览
     */
    openPreview = (attachmentId) => {
        this.state.previewId = attachmentId;
    }

    /**
     * 关闭预览
     */
    closePreview = () => {
        this.state.previewId = null;
    }

    /**
     * 获取当前预览的附件
     */
    getPreviewAttachment = () => {
        var self = this;
        if (!self.state.previewId) return null;
        return (self.props.attachments || []).find(function(a) { return a.id === self.state.previewId; });
    }

    /**
     * 处理删除
     */
    onRemoveClick = (attachmentId, event) => {
        event.stopPropagation();
        if (this.props.onRemove) {
            this.props.onRemove(attachmentId);
        }
    }

    /**
     * 下载文件
     */
    downloadFile = (attachmentId) => {
        var url = this.getContentUrl(attachmentId);
        var a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

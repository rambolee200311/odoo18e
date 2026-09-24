import base64

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError


MAX_MEDIA_COUNT = 20
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024


class QoolingMediaEvidenceMixin(models.AbstractModel):
    _name = "wd.qooling.media.evidence.mixin"
    _description = "Qooling Media Evidence Rules"

    @api.constrains("photo_ids")
    def _check_media_evidence(self):
        for record in self:
            if len(record.photo_ids) > MAX_MEDIA_COUNT:
                raise ValidationError(
                    _("A record can contain at most %(count)s media files.")
                    % {"count": MAX_MEDIA_COUNT}
                )
            for attachment in record.photo_ids:
                mimetype = attachment.mimetype or ""
                if not (mimetype.startswith("image/") or mimetype.startswith("video/")):
                    raise ValidationError(
                        _("Only image and video files can be used as evidence.")
                    )
                size = attachment.file_size
                if not size and attachment.datas:
                    size = len(base64.b64decode(attachment.datas))
                limit = MAX_VIDEO_SIZE if mimetype.startswith("video/") else MAX_IMAGE_SIZE
                if size > limit:
                    limit_mb = limit // (1024 * 1024)
                    raise ValidationError(
                        _("Media files of this type cannot exceed %(limit)s MB.")
                        % {"limit": limit_mb}
                    )

    def write(self, vals):
        if "photo_ids" in vals:
            locked = self.filtered(lambda record: record.state != "draft")
            if locked:
                raise UserError(_("Media evidence can only be changed while the record is a draft."))
        return super().write(vals)

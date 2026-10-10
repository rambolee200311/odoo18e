import base64

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError


MAX_MEDIA_COUNT = 20
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024
QOOLING_STATE_TRANSITION = object()


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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise UserError(_("Qooling records can only be created as drafts."))
        return super().create(vals_list)

    def write(self, vals):
        is_state_transition = self.env.context.get("qooling_state_transition") is QOOLING_STATE_TRANSITION
        if "state" in vals and not is_state_transition:
            raise UserError(_("Status can only be changed through a Qooling action."))
        if not is_state_transition:
            for record in self:
                if record.state != "draft" and set(vals) != {"photo_ids"}:
                    raise UserError(_("Only draft records can be changed."))
        return super().write(vals)

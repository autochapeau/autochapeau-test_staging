from odoo import models, fields, api


class HrDepartment(models.Model):
    _inherit = "hr.department"
    _sql_constraints = [
        (
            'hr_department_code_unique',
            'unique(code)',
            'The department code must be unique.',
        ),
    ]

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help='Analytic account related to this department.'
    )

    @api.model
    def _get_next_code(self):
        seq = self.env['ir.sequence'].browse(self.env.ref(
            'hr_branch_department.seq_hr_department_code').id)
        if seq:
            number_next = seq.number_next_actual
            prefix = seq.prefix or ''
            padding = seq.padding or 0
            code = f"{prefix}{str(number_next).zfill(padding)}"
            return code
        return 'New'

    code = fields.Char(
        string="Code",
        copy=False,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code') or vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'hr.department.code') or 'New'
        return super().create(vals_list)

    department_type = fields.Selection(
        [
            ("department", "Department"),
            ("branche", "Branche"),
            ("section", "Section"),
            ("division", "Division"),
            ("business_unit", "Business unit"),
        ],
        string="Department Type",
        default="department",
    )

    def _compute_plan_count(self):
        plans_data = self.env['mail.activity.plan']._read_group(
            domain=[
                '|',
                ('department_id', '=', False),
                ('department_id', 'in', self.ids)
            ],
            groupby=['department_id'],
            aggregates=['__count'],
        )
        plans_count = {}
        for row in plans_data:
            # row is normally a dict, but guard against unexpected tuple/tuple-like rows
            if isinstance(row, dict):
                key = row['department_id'][0] if row.get(
                    'department_id') else False
                cnt = row.get('__count', 0)
            else:
                # fallback: try to extract department id and count heuristically
                key = False
                cnt = 0
                try:
                    # row may be like (department_id, __count) or ((dept_id, name), __count)
                    if len(row) >= 2:
                        first = row[0]
                        last = row[-1]
                        if isinstance(first, (list, tuple)) and len(first) > 0:
                            key = first[0]
                        elif isinstance(first, int):
                            key = first
                        if isinstance(last, int):
                            cnt = last
                except Exception:
                    key = False
                    cnt = 0
            plans_count[key] = plans_count.get(key, 0) + cnt

        for department in self:
            department.plans_count = plans_count.get(
                department.id, 0) + plans_count.get(False, 0)

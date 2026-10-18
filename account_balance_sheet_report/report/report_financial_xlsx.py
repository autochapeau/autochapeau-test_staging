from odoo import _, models

HEADER_VALS1 = ["الحساب", "الدائن", "المدين", "الرصيد"]


class ReportFinancialXslx(models.AbstractModel):
    _name = "report.a_b_s.report_financial_xlsx"
    _description = "Report Financial XLSX"
    _inherit = "report.report_xlsx.abstract"

    # pylint: disable=unused-argument,too-many-locals,too-complex,too-many-statements
    def generate_xlsx_report(self, workbook, data, lines):
        """Generate report xlsx."""
        docs = self.env["accounting.reporting"].browse(lines.id)
        docids = {}
        res_data = self.env["report.account_balance_sheet_report.report_financial"]._get_report_values(
            docids, data)
        self = self.with_context(lang=self.env.user.lang)
        date_from = docs.date_from or " "
        date_to = docs.date_to or " "
        debit_credit = docs.debit_credit
        name_report = docs.account_report_id.name
        format_sheet = workbook.add_format(
            {
                "font_size": 14,
                "font_color": "white",
                "align": "center",
                "right": True,
                "left": True,
                "bottom": True,
                "top": True,
                "bold": True,
            }
        )
        format_sheet1 = workbook.add_format(
            {
                "font_size": 14,
                "bottom": True,
                "right": True,
                "left": True,
                "top": True,
                "bold": True,
            }
        )
        format_sheet1.set_align("center")
        format_sheet1.set_align("vcenter")
        format_sheet.set_bg_color(
            "#395870")  # pylint: disable=redefined-builtin
        font_size_12 = workbook.add_format(
            {
                "bottom": True,
                "top": True,
                "right": True,
                "bold": True,
                "left": True,
                "font_size": 14,
            }
        )
        font_size_12.set_align("right")
        font_size_10 = workbook.add_format(
            {
                "bottom": True,
                "top": True,
                "right": True,
                "bold": True,
                "left": True,
                "font_size": 12,
            }
        )
        font_size_10.set_align("right")
        format_sheet.set_bg_color(
            "#395870")  # pylint: disable=redefined-builtin
        font_size_8 = workbook.add_format(
            {"bottom": True, "top": True, "right": True, "left": True, "font_size": 10})
        font_size_8.set_align("right")
        font_size_center_8 = workbook.add_format(
            {"bottom": True, "top": True, "right": True,
                "left": True, "font_size": 10}
        )
        font_size_center_8.set_align("center")
        prod_row = 2
        if name_report == "Profit and Loss" and self.env.user.lang in (
            "ar_001",
            "ar_SY",
        ):
            sheet = workbook.add_worksheet(_("تقرير الأرباح و الخسائر"))
            sheet.right_to_left()
            sheet.merge_range(
                "A1:J2",
                (_("تقرير الأرباح و الخسائر: من %s")) % date_from
                + " " + (_("إلى  %s")) % date_to,
                format_sheet1,
            )
        elif name_report == "Profit and Loss" and self.env.user.lang not in (
            "ar_001",
            "ar_SY",
        ):
            sheet = workbook.add_worksheet(_("profit and loss report"))
            sheet.merge_range(
                "A1:J2",
                (_("Profit and loss report: from  %s")) % date_from
                + " " + (_("to  %s")) % date_to,
                format_sheet1,
            )
        elif name_report == "Balance Sheet" and self.env.user.lang in (
            "ar_001",
            "ar_SY",
        ):
            sheet = workbook.add_worksheet(_("تقرير الميزانية العمومية"))
            sheet.right_to_left()
            sheet.merge_range(
                "A1:J2",
                (_("تقرير الميزانية العمومية: من  %s")) % date_from
                + " " + (_("إلى  %s")) % date_to,
                format_sheet1,
            )
            sheet.merge_range(prod_row, 0, prod_row, 5, "الحساب", format_sheet)
            if debit_credit:
                sheet.merge_range(prod_row, 6, prod_row, 9,
                                  "الدائن", format_sheet)
                sheet.merge_range(prod_row, 10, prod_row,
                                  13, "المدين", format_sheet)
                sheet.merge_range(prod_row, 14, prod_row,
                                  17, "الرصيد", format_sheet)
            else:
                sheet.merge_range(prod_row, 6, prod_row, 9,
                                  "الرصيد", format_sheet)
        else:
            sheet = workbook.add_worksheet(_("Balance Sheet Report"))
            sheet.merge_range(
                "A1:R2",
                (_("Balance Sheet Report: from  %s")) % date_from
                + " " + (_("to  %s")) % date_to,
                format_sheet1,
            )
            sheet.merge_range(prod_row, 0, prod_row, 5,
                              HEADER_VALS1[0], format_sheet)
            if debit_credit:
                sheet.merge_range(prod_row, 6, prod_row, 9,
                                  HEADER_VALS1[1], format_sheet)
                sheet.merge_range(prod_row, 10, prod_row, 13,
                                  HEADER_VALS1[2], format_sheet)
                sheet.merge_range(prod_row, 14, prod_row, 17,
                                  HEADER_VALS1[3], format_sheet)
            else:
                sheet.merge_range(prod_row, 6, prod_row, 9,
                                  HEADER_VALS1[3], format_sheet)
        # Set header.
        prod_row += 1
        # set lines
        lines = res_data.get("get_account_lines") or []
        formats = {
            "header_name": font_size_12,
            "header_amount": font_size_12,
            "line_name": font_size_center_8,
            "line_amount": font_size_8,
        }
        # Analytic filter returns blocks ({analytic, lines, totals}), not flat rows.
        if lines and isinstance(lines[0], dict) and lines[0].get("analytic"):
            for block in lines:
                prod_row = self._write_analytic_block(
                    sheet, prod_row, block, debit_credit, formats
                )
        else:
            for line in lines:
                prod_row = self._write_financial_line(
                    sheet, prod_row, line, debit_credit, formats
                )

    def _line_level(self, line):
        level = line.get("level") or 0
        try:
            return int(level)
        except (TypeError, ValueError):
            return 0

    def _write_amount_cells(self, sheet, row, line, debit_credit, amount_fmt):
        balance = line.get("balance") or 0.0
        if debit_credit:
            sheet.merge_range(
                row, 6, row, 9, "%.2f" % (line.get("credit") or 0.0), amount_fmt
            )
            sheet.merge_range(
                row, 10, row, 13, "%.2f" % (line.get("debit") or 0.0), amount_fmt
            )
            sheet.merge_range(row, 14, row, 17, "%.2f" % balance, amount_fmt)
        else:
            sheet.merge_range(row, 6, row, 9, "%.2f" % balance, amount_fmt)

    def _write_financial_line(self, sheet, row, line, debit_credit, formats):
        """Write one report row. Level 0 uses the header style."""
        is_header = self._line_level(line) == 0
        name_fmt = formats["header_name"] if is_header else formats["line_name"]
        amount_fmt = formats["header_amount"] if is_header else formats["line_amount"]
        sheet.merge_range(row, 0, row, 5, line.get("name") or "", name_fmt)
        self._write_amount_cells(sheet, row, line, debit_credit, amount_fmt)
        return row + 1

    def _write_labeled_total(self, sheet, row, label, amount, formats):
        sheet.merge_range(row, 0, row, 5, label, formats["header_name"])
        sheet.merge_range(
            row, 6, row, 9, "%.2f" % (amount or 0.0), formats["header_amount"]
        )
        return row + 1

    def _write_analytic_block(self, sheet, row, block, debit_credit, formats):
        """Write one analytic section, or the closing TOTAL block."""
        if block.get("is_total"):
            sheet.merge_range(
                row, 0, row, 5, _("TOTAL"), formats["header_name"]
            )
            row += 1
            row = self._write_labeled_total(
                sheet, row, _("Income"), block.get("income_total"), formats
            )
            row = self._write_labeled_total(
                sheet, row, _("Expenses"), block.get("expense_total"), formats
            )
            return self._write_labeled_total(
                sheet, row, _("Balance"), block.get("balance_total"), formats
            )

        sheet.merge_range(
            row,
            0,
            row,
            5,
            _("Analytic Account: %s") % (block.get("analytic") or ""),
            formats["header_name"],
        )
        row += 1
        for line in block.get("lines") or []:
            row = self._write_financial_line(
                sheet, row, line, debit_credit, formats
            )
        return row + 1

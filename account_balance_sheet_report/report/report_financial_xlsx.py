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
        lines = res_data.get("get_account_lines")
        for line in lines:
            if int(line["level"]) == 0:
                sheet.merge_range(prod_row, 0, prod_row, 5,
                                  line["name"], font_size_12)
                if debit_credit:
                    sheet.merge_range(prod_row, 6, prod_row,
                                      9, "%.2f" % line["credit"], font_size_12)
                    sheet.merge_range(prod_row, 10, prod_row,
                                      13, "%.2f" % line["debit"], font_size_12)
                    sheet.merge_range(
                        prod_row,
                        14,
                        prod_row,
                        17,
                        "%.2f" % line["balance"],
                        font_size_12,
                    )
                else:
                    sheet.merge_range(prod_row, 6, prod_row, 9,
                                      "%.2f" % line["balance"], font_size_12)
            else:
                sheet.merge_range(prod_row, 0, prod_row, 5,
                                  line["name"], font_size_center_8)
                if debit_credit:
                    sheet.merge_range(prod_row, 6, prod_row,
                                      9, "%.2f" % line["credit"], font_size_8)
                    sheet.merge_range(prod_row, 10, prod_row,
                                      13, "%.2f" % line["debit"], font_size_8)
                    sheet.merge_range(
                        prod_row,
                        14,
                        prod_row,
                        17,
                        "%.2f" % line["balance"],
                        font_size_8,
                    )
                else:
                    sheet.merge_range(prod_row, 6, prod_row,
                                      9, "%.2f" % line["balance"], font_size_8)

            prod_row = prod_row + 1

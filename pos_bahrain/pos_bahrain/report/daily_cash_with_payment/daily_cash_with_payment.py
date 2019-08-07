# Copyright (c) 2013, 	9t9it and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from functools import partial
from toolz import groupby, pluck


def execute(filters=None):
	mop = _get_mop()

	columns = _get_columns(mop, filters)
	data = _get_data(_get_clauses(), filters, mop)

	return columns, data


def _get_columns(mop, filters):
	summary_view = filters.get('summary_view')
	columns = []

	def make_column(key, label=None, type="Data", options=None, width=120):
		return {
			"label": _(label or key.replace("_", " ").title()),
			"fieldname": key,
			"fieldtype": type,
			"options": options,
			"width": width
		}

	if not summary_view:
		columns.append(
			make_column("invoice", type="Link", options="Sales Invoice")
		)

	columns.append(make_column("posting_date", "Date", type="Date"))

	if not summary_view:
		columns.append(
			make_column("posting_time", "Time", type="Time")
		)

	def make_mop_column(row):
		return make_column(
			row.replace(" ", "_").lower(),
			type="Float"
		)

	columns.extend(
		list(map(make_mop_column, mop))
		+ [make_column("total", type="Float")]
	)

	return columns


def _get_data(clauses, filters, mop):
	result = frappe.db.sql(
		"""
			SELECT
				si.name AS invoice,
				si.posting_date AS posting_date,
				si.posting_time AS posting_time,
				si.change_amount AS change_amount,
				sip.mode_of_payment AS mode_of_payment,
				sip.amount AS amount
			FROM `tabSales Invoice` AS si 
			RIGHT JOIN `tabSales Invoice Payment` AS sip ON
				sip.parent = si.name
			WHERE {clauses}
		""".format(
			clauses=clauses
		),
		values=filters,
		as_dict=1
	)

	result = _sum_invoice_payments(
		groupby('invoice', result),
		mop
	)

	if filters.get('summary_view'):
		result = _summarize_payments(
			groupby('posting_date', result),
			mop
		)

	return result


def _summarize_payments(result, mop):
	summary = []

	mop_cols = [
		mop_col.replace(" ", "_").lower()
		for mop_col in mop
	]

	def make_summary_row(_, row):
		for col in mop_cols:
			_[col] = _[col] + row[col]

		_['posting_time'] = None
		_['invoice'] = None

		return _

	for key, payments in result.iteritems():
		summary.append(
			reduce(make_summary_row, payments)
		)

	return summary


def _sum_invoice_payments(invoice_payments, mop):
	data = []

	mop_cols = list(
		map(lambda x: x.replace(" ", "_").lower(), mop)
	)

	def make_change_total(row):
		row['cash'] = row.get('cash') - row.get('change')
		row['total'] = sum([
			row[mop_col] for mop_col in mop_cols
		])

		for mop_col in (mop_cols + ['total']):
			row[mop_col] = round(row.get(mop_col), 3)

		return row

	make_payment_row = partial(_make_payment_row, mop)

	for key, payments in invoice_payments.iteritems():
		invoice_payment_row = reduce(
			make_payment_row,
			payments,
			_new_invoice_payment(mop_cols)
		)

		data.append(
			make_change_total(invoice_payment_row)
		)

	return data


def _get_clauses():
	clauses = [
		"si.docstatus = 1",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
	]
	return " AND ".join(clauses)


def _make_payment_row(mop_cols, _, row):
	mop = row.get('mode_of_payment')
	amount = row.get('amount')

	for mop_col in mop_cols:
		mop_key = mop_col.replace(" ", "_").lower()
		if mop == mop_col:
			_[mop_key] = _[mop_key] + amount
			break

	if not _.get('invoice'):
		_['invoice'] = row.get('invoice')
	if not _.get('change'):
		_['change'] = row.get('change_amount')
	if not _.get('posting_date'):
		_['posting_date'] = row.get('posting_date')
	if not _.get('posting_time'):
		_['posting_time'] = row.get('posting_time')

	return _


def _get_mop():
	mop = frappe.get_all('POS Bahrain Settings MOP', fields=['mode_of_payment'])

	if not mop:
		frappe.throw(_('Please set Report MOP under POS Bahrain Settings'))

	return list(pluck('mode_of_payment', mop))


def _new_invoice_payment(mop_cols):
	invoice_payment = {
		'invoice': None,
		'posting_date': None,
		'posting_time': None,
		'change': None,
		'total': 0.00
	}

	for mop_col in mop_cols:
		invoice_payment[mop_col] = 0.00

	return invoice_payment

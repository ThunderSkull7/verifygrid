import type { ExceptionCluster, VerificationResultItem } from '../types';

export function computeLocalClusters(items: VerificationResultItem[]): ExceptionCluster[] {
  const map: Record<string, ExceptionCluster> = {};
  for (const item of items) {
    const reason = String(
      item.reason_code || (item.field_differences?.[0]?.reason_code) || item.match_status || 'FIELD_MISMATCH'
    );
    const cat = String(item.discrepancy_category || 'field_mismatch');
    const cid = `c_${reason}_${cat}`.toLowerCase().replace(/[^a-z0-9_]/g, '_');
    const exposure = item.exposure_amount ?? 0;
    const fields = (item.field_differences || []).map((f) => f.field_name);

    if (!map[cid]) {
      const fieldTitle = fields.length > 0 ? fields.map((f) => f.replace(/_/g, ' ')).join(', ') : 'Record';
      let cName = `${reason.replace(/_/g, ' ')} in ${fieldTitle}`;
      if (reason.includes('WHITESPACE')) cName = `Trailing Whitespace Mismatch in ${fieldTitle}`;
      else if (reason.includes('DATE')) cName = `Date Lag Exceeded (>3 Days) on Gateway Settlement`;
      else if (reason.includes('MISSING')) cName = `Missing Records in Dataset (${fieldTitle})`;
      else if (reason.includes('PARTIAL') || reason.includes('OVERPAYMENT')) cName = `Split Payment Installment Variance`;
      else if (reason.includes('TAX')) cName = `Missing Tax Code in ERP Source`;

      map[cid] = {
        cluster_id: cid,
        cluster_name: cName,
        reason_code: reason,
        rule_id: item.field_differences?.[0]?.rule_id,
        failed_field_names: fields,
        discrepancy_category: cat,
        severity: item.severity || 'medium',
        total_records: 0,
        total_exposure: 0,
        currency: item.currency || 'USD',
        root_cause_explanation: `${reason} across fields [${fields.join(', ')}]`,
        status_counts: {},
        discrepancy_ids: [],
        assigned_to: item.assigned_to || undefined,
      };
    }
    const cl = map[cid];
    cl.total_records += 1;
    cl.total_exposure = Math.round((cl.total_exposure + exposure) * 100) / 100;
    if (item.id) cl.discrepancy_ids?.push(item.id);
    const st = item.resolution_status || 'unresolved';
    cl.status_counts[st] = (cl.status_counts[st] || 0) + 1;
    if (item.severity === 'BLOCKING' || item.severity === 'high') cl.severity = item.severity;
  }
  return Object.values(map).sort((a, b) => b.total_exposure - a.total_exposure);
}

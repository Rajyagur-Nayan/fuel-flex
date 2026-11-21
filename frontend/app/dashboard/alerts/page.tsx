'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bell,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ShieldAlert,
  Filter,
  RefreshCw,
  User,
  MapPin,
  Check,
  AlertCircle,
  Sliders,
  Save,
  X,
  ChevronRight,
} from 'lucide-react';
import {
  getAlerts,
  acknowledgeAlert,
  resolveAlert,
  getEmployees,
  getWorkstations,
  getAlertConfig,
  updateAlertConfig,
} from '@/lib/attendanceApi';
import { toast } from '@/components/feedback/Toast';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [workstations, setWorkstations] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Configurable Absence Threshold (Default: 15 minutes)
  const [thresholdMinutes, setThresholdMinutes] = useState<number>(15);
  const [savingThreshold, setSavingThreshold] = useState<boolean>(false);

  // Filters
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [filterEmpId, setFilterEmpId] = useState<string>('');
  const [filterShift, setFilterShift] = useState<string>('');
  const [filterDate, setFilterDate] = useState<string>('');

  // Action modal
  const [selectedAlert, setSelectedAlert] = useState<any | null>(null);
  const [modalAction, setModalAction] = useState<'acknowledge' | 'resolve' | null>(null);
  const [actionNotes, setActionNotes] = useState<string>('');
  const [actionOperator, setActionOperator] = useState<string>('Manager');
  const [submittingAction, setSubmittingAction] = useState(false);

  // Load choices and threshold once on mount
  useEffect(() => {
    getEmployees().then((data) => setEmployees(data || [])).catch(() => {});
    getWorkstations().then((data) => setWorkstations(data || [])).catch(() => {});
    getAlertConfig().then((data) => {
      if (data?.absence_threshold_minutes) {
        setThresholdMinutes(data.absence_threshold_minutes);
      }
    }).catch(() => {});
  }, []);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (filterStatus !== 'ALL') params.status = filterStatus;
      if (filterEmpId) params.employee_id = filterEmpId;
      if (filterShift) params.shift = filterShift;
      if (filterDate) params.date = filterDate;

      const alertsRes = await getAlerts(params);
      setAlerts(alertsRes?.alerts || []);
    } catch (err: any) {
      toast.error('Failed to load alerts', err.message);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterEmpId, filterShift, filterDate]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  const handleUpdateThreshold = async (minutes: number) => {
    setSavingThreshold(true);
    try {
      await updateAlertConfig(minutes);
      setThresholdMinutes(minutes);
      toast.success(`Absence alarm threshold set to ${minutes} minutes`);
    } catch (err: any) {
      toast.error('Failed to update threshold', err.message);
    } finally {
      setSavingThreshold(false);
    }
  };

  const handleActionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAlert || !modalAction) return;

    setSubmittingAction(true);
    try {
      if (modalAction === 'acknowledge') {
        await acknowledgeAlert(selectedAlert.id, actionOperator, actionNotes);
        toast.info(`Alert #${selectedAlert.id} acknowledged`);
      } else if (modalAction === 'resolve') {
        await resolveAlert(selectedAlert.id, actionOperator, actionNotes);
        toast.success(`Alert #${selectedAlert.id} resolved`);
      }
      setSelectedAlert(null);
      setModalAction(null);
      setActionNotes('');
      loadAlerts();
    } catch (err: any) {
      toast.error(err.message || 'Action failed');
    } finally {
      setSubmittingAction(false);
    }
  };

  const activeCount = alerts.filter((a) => a.status === 'ACTIVE').length;
  const acknowledgedCount = alerts.filter((a) => a.status === 'ACKNOWLEDGED').length;
  const resolvedCount = alerts.filter((a) => a.status === 'RESOLVED').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
            <ShieldAlert className="h-4 w-4" />
            <span>Position Absence Enforcement</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
            Absence & Position Alerts
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Automatic alarms triggered when active, attendance-verified employees leave workstations beyond {thresholdMinutes} minutes
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href="/dashboard/workstations"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <Clock className="h-4 w-4 text-primary" /> Workstations
          </Link>
          <button
            onClick={loadAlerts}
            disabled={loading}
            className="p-2.5 rounded-xl border border-slate-200 hover:border-primary text-slate-500 hover:text-primary transition-all"
            title="Refresh Alerts"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metrics & Threshold Slider */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Active Alarms
            </span>
            <div className="h-9 w-9 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center">
              <AlertTriangle className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-rose-600 mt-2">{activeCount}</div>
          <p className="text-xs text-slate-400 mt-1">Requires supervisor attention</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Acknowledged
            </span>
            <div className="h-9 w-9 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <Clock className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{acknowledgedCount}</div>
          <p className="text-xs text-slate-400 mt-1">Noted by supervisor</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Resolved Today
            </span>
            <div className="h-9 w-9 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{resolvedCount}</div>
          <p className="text-xs text-slate-400 mt-1">Returned or closed</p>
        </div>

        {/* Configurable Threshold Card */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Alarm Threshold
            </span>
            <span className="text-xs font-bold text-primary font-mono px-2 py-0.5 rounded-lg bg-orange-50 border border-orange-200">
              {thresholdMinutes} min
            </span>
          </div>

          <div className="grid grid-cols-4 gap-1.5 mt-2">
            {[5, 10, 15, 30].map((m) => (
              <button
                key={m}
                onClick={() => handleUpdateThreshold(m)}
                disabled={savingThreshold}
                className={`py-1.5 rounded-lg text-xs font-bold transition-all ${
                  thresholdMinutes === m
                    ? 'bg-primary text-white shadow-brand'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {m}m
              </button>
            ))}
          </div>

          <span className="text-[11px] text-slate-400 mt-1">
            Continuous absence trigger threshold
          </span>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-white rounded-2xl p-4 border border-slate-100 shadow-card flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {['ALL', 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'].map((st) => (
            <button
              key={st}
              onClick={() => setFilterStatus(st)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                filterStatus === st
                  ? 'bg-primary text-white shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={filterEmpId}
            onChange={(e) => setFilterEmpId(e.target.value)}
            className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs bg-white text-slate-800 outline-none focus:border-primary"
          >
            <option value="">All Employees</option>
            {employees.map((e) => (
              <option key={e.employee_id} value={e.employee_id}>
                {e.name} ({e.employee_id})
              </option>
            ))}
          </select>

          <input
            type="date"
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs bg-white text-slate-800 outline-none focus:border-primary"
          />
        </div>
      </div>

      {/* Alerts Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">Position Alerts Registry</h3>
          <span className="text-xs text-slate-500 font-medium">{alerts.length} alerts recorded</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-100 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                <th className="px-6 py-3.5">Employee</th>
                <th className="px-6 py-3.5">Workstation</th>
                <th className="px-6 py-3.5">Absent Since</th>
                <th className="px-6 py-3.5">Absence Duration</th>
                <th className="px-6 py-3.5">Status</th>
                <th className="px-6 py-3.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm text-slate-700">
              {loading && alerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    <RefreshCw className="h-6 w-6 animate-spin text-primary mx-auto mb-2" />
                    <span>Loading absence alerts...</span>
                  </td>
                </tr>
              ) : alerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    <CheckCircle2 className="h-8 w-8 text-emerald-400 mx-auto mb-2" />
                    <span className="font-medium text-slate-600">
                      No absence alerts found. All employees complying with assigned positions!
                    </span>
                  </td>
                </tr>
              ) : (
                alerts.map((alert) => {
                  const isActive = alert.status === 'ACTIVE';
                  const isAck = alert.status === 'ACKNOWLEDGED';
                  const isRes = alert.status === 'RESOLVED';
                  const durMin = Math.round((alert.absence_duration_seconds || 0) / 60);

                  return (
                    <tr key={alert.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-3.5">
                        <div className="font-semibold text-slate-900">
                          {alert.employee_name || alert.employee_id}
                        </div>
                        <div className="text-xs font-mono text-slate-500">{alert.employee_id}</div>
                      </td>
                      <td className="px-6 py-3.5">
                        <span className="font-medium text-slate-800">
                          {alert.workstation_name || `Station #${alert.workstation_id}`}
                        </span>
                        <div className="text-xs text-slate-400">{alert.shift || 'General Shift'}</div>
                      </td>
                      <td className="px-6 py-3.5 font-medium text-slate-900">
                        {alert.absent_since ? format(new Date(alert.absent_since), 'PP p') : '--'}
                      </td>
                      <td className="px-6 py-3.5 font-mono font-bold text-rose-600">
                        {durMin} min absence
                      </td>
                      <td className="px-6 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                            isActive
                              ? 'bg-rose-50 text-rose-700 border border-rose-200 animate-pulse'
                              : isAck
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          }`}
                        >
                          {isActive ? (
                            <AlertTriangle className="h-3 w-3" />
                          ) : isAck ? (
                            <Clock className="h-3 w-3" />
                          ) : (
                            <Check className="h-3 w-3" />
                          )}
                          {alert.status}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-right">
                        {isActive && (
                          <div className="inline-flex items-center gap-1.5">
                            <button
                              onClick={() => {
                                setSelectedAlert(alert);
                                setModalAction('acknowledge');
                                setActionNotes('');
                              }}
                              className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200"
                            >
                              Acknowledge
                            </button>
                            <button
                              onClick={() => {
                                setSelectedAlert(alert);
                                setModalAction('resolve');
                                setActionNotes('');
                              }}
                              className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
                            >
                              Resolve
                            </button>
                          </div>
                        )}
                        {isAck && (
                          <button
                            onClick={() => {
                              setSelectedAlert(alert);
                              setModalAction('resolve');
                              setActionNotes('');
                            }}
                            className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
                          >
                            Resolve
                          </button>
                        )}
                        {isRes && (
                          <span className="text-xs text-slate-400">
                            By {alert.resolved_by || 'Supervisor'}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Acknowledge / Resolve Modal */}
      <AnimatePresence>
        {selectedAlert && modalAction && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => {
                setSelectedAlert(null);
                setModalAction(null);
              }}
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-md bg-white rounded-2xl p-6 shadow-2xl border border-slate-100 z-10"
            >
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <ShieldAlert className="h-5 w-5 text-primary" />
                  {modalAction === 'acknowledge' ? 'Acknowledge Alert' : 'Resolve Alert'} #
                  {selectedAlert.id}
                </h3>
                <button
                  onClick={() => {
                    setSelectedAlert(null);
                    setModalAction(null);
                  }}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleActionSubmit} className="space-y-4">
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-100 text-xs space-y-1">
                  <div>
                    <span className="text-slate-500">Employee:</span>{' '}
                    <span className="font-bold text-slate-800">
                      {selectedAlert.employee_name || selectedAlert.employee_id} (
                      {selectedAlert.employee_id})
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Workstation:</span>{' '}
                    <span className="font-bold text-slate-800">
                      {selectedAlert.workstation_name || `Station #${selectedAlert.workstation_id}`}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Operator Name</label>
                  <input
                    type="text"
                    value={actionOperator}
                    onChange={(e) => setActionOperator(e.target.value)}
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Notes / Reason</label>
                  <input
                    type="text"
                    value={actionNotes}
                    onChange={(e) => setActionNotes(e.target.value)}
                    required
                    placeholder="e.g. Employee returned to desk / brief customer support assistance"
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedAlert(null);
                      setModalAction(null);
                    }}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingAction}
                    className={`px-5 py-2 rounded-xl text-xs font-semibold text-white shadow-brand ${
                      modalAction === 'acknowledge'
                        ? 'bg-amber-500 hover:bg-amber-600'
                        : 'bg-emerald-600 hover:bg-emerald-700'
                    }`}
                  >
                    {submittingAction
                      ? 'Saving...'
                      : modalAction === 'acknowledge'
                      ? 'Confirm Acknowledgment'
                      : 'Confirm Resolution'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

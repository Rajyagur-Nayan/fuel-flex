'use client';

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Monitor,
  User,
  Clock,
  Play,
  Square,
  AlertTriangle,
  CheckCircle2,
  PauseCircle,
  Timer,
  Edit2,
  RefreshCw,
  Video,
  Coffee,
  ShieldAlert,
  Trash2,
  Sliders,
  ChevronRight,
  ShieldCheck,
  X,
} from 'lucide-react';
import {
  BACKEND_URL,
  getWorkstations,
  getEmployees,
  startWorkstationSession,
  stopWorkstationSession,
  getWorkstationIntervals,
  updateWorkstation,
  correctWorkstationInterval,
  resetWorkstationTodayTime,
  startWorkstationBreak,
  stopWorkstationBreak,
  startWorkstationCamera,
  stopWorkstationCamera,
  getWorkstationCameraStatus,
  getAlertConfig,
  updateAlertConfig,
  updateWorkstationThreshold,
} from '@/lib/attendanceApi';
import { toast } from '@/components/feedback/Toast';

export default function WorkstationsPage() {
  const [workstations, setWorkstations] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [selectedWsId, setSelectedWsId] = useState<number | null>(null);
  const [selectedEmpId, setSelectedEmpId] = useState<string>('');
  const [intervals, setIntervals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [isSystemRunning, setIsSystemRunning] = useState<boolean>(false);
  const [systemActionLoading, setSystemActionLoading] = useState<boolean>(false);
  const [selectedShift, setSelectedShift] = useState<string>('General Shift');

  // Interval correction modal
  const [editingInterval, setEditingInterval] = useState<any | null>(null);
  const [correctionDuration, setCorrectionDuration] = useState<string>('');
  const [correctionNote, setCorrectionNote] = useState<string>('');

  // Break modal
  const [breakModalOpen, setBreakModalOpen] = useState<boolean>(false);
  const [breakType, setBreakType] = useState<string>('Lunch Break');
  const [breakNotes, setBreakNotes] = useState<string>('');
  const [breakLoading, setBreakLoading] = useState<boolean>(false);

  // Absence Alert Threshold
  const [absenceThresholdMin, setAbsenceThresholdMin] = useState<number>(15);
  const [savingThreshold, setSavingThreshold] = useState<boolean>(false);

  // Telemetry state
  const [telemetry, setTelemetry] = useState<any>({
    is_monitoring: false,
    status: 'STOPPED',
    employee_id: null,
    employee_name: null,
    total_active_seconds: 0,
    total_active_formatted: '00h 00m 00s',
    grace_remaining_seconds: 0,
    grace_period_total: 60,
    last_confirmed_presence: 'None',
    is_camera_connected: true,
  });

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (selectedWsId) {
      loadWorkstationDetails(selectedWsId);
      setupWorkstationWebSocket(selectedWsId);
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [selectedWsId]);

  useEffect(() => {
    if (selectedWsId && selectedEmpId) {
      loadIntervals(selectedWsId, selectedEmpId);
    }
  }, [selectedWsId, selectedEmpId]);

  const loadInitialData = async () => {
    try {
      const [wsList, empList, alertConfig] = await Promise.all([
        getWorkstations(),
        getEmployees(),
        getAlertConfig().catch(() => null),
      ]);

      setWorkstations(wsList || []);
      setEmployees(empList || []);

      if (alertConfig?.absence_threshold_minutes) {
        setAbsenceThresholdMin(alertConfig.absence_threshold_minutes);
      }

      if (wsList && wsList.length > 0) {
        setSelectedWsId(wsList[0].id);
      }
      if (empList && empList.length > 0) {
        setSelectedEmpId(empList[0].employee_id);
      }
    } catch (e: any) {
      console.error('Initial data load notice:', e);
    }
  };

  const loadWorkstationDetails = async (id: number) => {
    try {
      const ws = await getWorkstations();
      const current = ws?.find((w: any) => w.id === id);
      if (current) {
        if (current.alert_threshold_seconds) {
          setAbsenceThresholdMin(Math.round(current.alert_threshold_seconds / 60));
        }
      }
    } catch {}
  };

  const loadIntervals = async (wsId: number, empId: string) => {
    setLoading(true);
    try {
      const today = format(new Date(), 'yyyy-MM-dd');
      const data = await getWorkstationIntervals(wsId, empId, today);
      setIntervals(data || []);
    } catch (err: any) {
      console.warn('Interval load notice:', err.message);
    } finally {
      setLoading(false);
    }
  };

  const setupWorkstationWebSocket = (wsId: number) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const host = typeof window !== 'undefined' ? window.location.hostname || '127.0.0.1' : '127.0.0.1';
    const wsUrl = `ws://${host}:8000/ws/workstation`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'telemetry') {
            setTelemetry((prev: any) => ({
              ...prev,
              ...msg,
            }));
            setIsSystemRunning(msg.status === 'ACTIVE' || msg.status === 'PENDING_ABSENCE');
            if (msg.employee_id && msg.employee_id !== selectedEmpId) {
              setSelectedEmpId(msg.employee_id);
            }
          }
        } catch {}
      };

      ws.onclose = () => {
        // ws reconnect handled if needed
      };
    } catch {}
  };

  const handleStartSession = async () => {
    if (!selectedWsId || !selectedEmpId) {
      toast.error('Select both workstation and employee');
      return;
    }
    setSystemActionLoading(true);
    try {
      await startWorkstationSession(
        selectedWsId,
        selectedEmpId,
        'supervisor',
        selectedShift,
        true
      );
      toast.success(`Workstation session started for ${selectedEmpId}`);
      setIsSystemRunning(true);
      loadIntervals(selectedWsId, selectedEmpId);
    } catch (err: any) {
      toast.error(err.message || 'Failed to start session');
    } finally {
      setSystemActionLoading(false);
    }
  };

  const handleStopSession = async () => {
    if (!selectedWsId) return;
    setSystemActionLoading(true);
    try {
      await stopWorkstationSession(selectedWsId, 'supervisor');
      toast.info('Workstation session stopped cleanly');
      setIsSystemRunning(false);
      if (selectedEmpId) {
        loadIntervals(selectedWsId, selectedEmpId);
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to stop session');
    } finally {
      setSystemActionLoading(false);
    }
  };

  const handleSaveThreshold = async (minutes: number) => {
    setSavingThreshold(true);
    try {
      if (selectedWsId) {
        await updateWorkstationThreshold(selectedWsId, minutes);
      }
      await updateAlertConfig(minutes);
      setAbsenceThresholdMin(minutes);
      toast.success(`Absence alert threshold updated to ${minutes} minutes`);
    } catch (err: any) {
      toast.error(err.message || 'Failed to save threshold');
    } finally {
      setSavingThreshold(false);
    }
  };

  const handleStartBreak = async () => {
    if (!selectedWsId) return;
    setBreakLoading(true);
    try {
      await startWorkstationBreak(selectedWsId, breakType, 'supervisor', breakNotes);
      toast.success(`Workstation placed on ${breakType}`);
      setBreakModalOpen(false);
    } catch (err: any) {
      toast.error(err.message || 'Failed to start break');
    } finally {
      setBreakLoading(false);
    }
  };

  const handleStopBreak = async () => {
    if (!selectedWsId) return;
    setBreakLoading(true);
    try {
      await stopWorkstationBreak(selectedWsId, 'supervisor');
      toast.success('Break ended. Active workstation monitoring resumed.');
    } catch (err: any) {
      toast.error(err.message || 'Failed to stop break');
    } finally {
      setBreakLoading(false);
    }
  };

  const handleCorrectionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingInterval || !selectedWsId) return;

    const durSec = parseFloat(correctionDuration);
    if (isNaN(durSec) || durSec < 0) {
      toast.error('Enter a valid duration in seconds');
      return;
    }

    try {
      await correctWorkstationInterval(selectedWsId, {
        interval_id: editingInterval.id,
        duration_seconds: durSec,
        notes: correctionNote || 'Supervisor adjusted interval time',
        operator: 'supervisor',
      });
      toast.success('Interval updated and daily total recalculated');
      setEditingInterval(null);
      if (selectedEmpId) {
        loadIntervals(selectedWsId, selectedEmpId);
      }
    } catch (err: any) {
      toast.error(err.message || 'Interval correction failed');
    }
  };

  const handleResetDailyTime = async () => {
    if (!selectedWsId) return;
    if (!confirm("Are you sure you want to reset today's presence time for this workstation?")) {
      return;
    }
    try {
      await resetWorkstationTodayTime(selectedWsId, selectedEmpId || undefined);
      toast.info("Today's workstation presence time has been reset to zero");
      if (selectedEmpId) {
        loadIntervals(selectedWsId, selectedEmpId);
      }
    } catch (err: any) {
      toast.error(err.message || 'Reset failed');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
            <Monitor className="h-4 w-4" />
            <span>Precision Computer Vision Tracking</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
            Workstation Presence & Hours
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Real-time working hours calculation, absence grace period monitoring, and break tracking
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Link
            href="/dashboard/alerts"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <ShieldAlert className="h-4 w-4 text-amber-500" /> Absence Alerts
          </Link>

          <Link
            href="/dashboard/workstation-reports"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <Clock className="h-4 w-4 text-primary" /> Daily Reports
          </Link>
        </div>
      </div>

      {/* Main Control Panel & Live Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Session Control & Station Selection */}
        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-card space-y-5">
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Monitor className="h-5 w-5 text-primary" /> Workstation Assignment
          </h3>

          <div>
            <label className="text-xs font-semibold text-slate-700 mb-1.5 block">Select Station</label>
            <select
              value={selectedWsId || ''}
              onChange={(e) => setSelectedWsId(Number(e.target.value))}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
            >
              {workstations.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.code} — {w.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 mb-1.5 block">Assigned Employee</label>
            <select
              value={selectedEmpId}
              onChange={(e) => setSelectedEmpId(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
            >
              {employees.map((emp) => (
                <option key={emp.employee_id} value={emp.employee_id}>
                  {emp.name} ({emp.employee_id})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 mb-1.5 block">Shift Assignment</label>
            <select
              value={selectedShift}
              onChange={(e) => setSelectedShift(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
            >
              <option value="General Shift">General Shift (09:00 - 18:00)</option>
              <option value="Day Shift">Day Shift (09:00 - 18:00)</option>
              <option value="Morning Shift">Morning Shift (06:00 - 14:00)</option>
              <option value="Evening Shift">Evening Shift (14:00 - 22:00)</option>
              <option value="Night Shift">Night Shift (20:00 - 05:00)</option>
            </select>
          </div>

          {/* Session Action Buttons */}
          <div className="pt-2 flex flex-col gap-2">
            {!isSystemRunning ? (
              <button
                onClick={handleStartSession}
                disabled={systemActionLoading}
                className="w-full py-3 rounded-xl font-semibold text-sm bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-500/20 flex items-center justify-center gap-2 transition-all cursor-pointer"
              >
                <Play className="h-4 w-4 fill-current" /> Start Workstation Session
              </button>
            ) : (
              <div className="flex flex-col gap-2">
                <button
                  onClick={handleStopSession}
                  disabled={systemActionLoading}
                  className="w-full py-3 rounded-xl font-semibold text-sm bg-rose-600 hover:bg-rose-700 text-white shadow-md shadow-rose-500/20 flex items-center justify-center gap-2 transition-all cursor-pointer"
                >
                  <Square className="h-4 w-4 fill-current" /> Stop Workstation Session
                </button>

                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setBreakModalOpen(true)}
                    className="py-2.5 rounded-xl font-semibold text-xs bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                  >
                    <Coffee className="h-3.5 w-3.5" /> Take Break
                  </button>
                  <button
                    onClick={handleStopBreak}
                    className="py-2.5 rounded-xl font-semibold text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" /> End Break
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Center: Real-Time Precision Telemetry */}
        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-card flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Workstation Telemetry
              </span>
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${
                  telemetry.status === 'ACTIVE'
                    ? 'bg-emerald-50 text-emerald-600 border border-emerald-200'
                    : telemetry.status === 'PENDING_ABSENCE'
                    ? 'bg-amber-50 text-amber-600 border border-amber-200 animate-pulse'
                    : telemetry.status === 'ON_BREAK'
                    ? 'bg-blue-50 text-blue-600 border border-blue-200'
                    : 'bg-slate-100 text-slate-600'
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    telemetry.status === 'ACTIVE'
                      ? 'bg-emerald-500'
                      : telemetry.status === 'PENDING_ABSENCE'
                      ? 'bg-amber-500'
                      : 'bg-slate-400'
                  }`}
                />
                {telemetry.status || 'STOPPED'}
              </span>
            </div>

            <div className="py-6 text-center">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Total Active Hours Today
              </span>
              <div className="text-4xl font-extrabold font-mono text-slate-900 mt-2 tracking-tight">
                {telemetry.total_active_formatted || '00h 00m 00s'}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Monotonically accumulated non-overlapping presence
              </p>
            </div>

            {/* Grace Period Progress Bar */}
            <div className="space-y-1.5 bg-slate-50 rounded-xl p-3 border border-slate-100">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-600">Absence Grace Tolerance</span>
                <span className="font-mono font-bold text-slate-800">
                  {telemetry.grace_remaining_seconds || 0}s remaining
                </span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(
                      100,
                      Math.max(
                        0,
                        ((telemetry.grace_remaining_seconds || 0) /
                          (telemetry.grace_period_total || 60)) *
                          100
                      )
                    )}%`,
                  }}
                />
              </div>
              <span className="text-[11px] text-slate-400">
                Resets to 60s when recognized in workstation zone
              </span>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs">
            <span className="text-slate-500">Last presence verified:</span>
            <span className="font-semibold text-slate-800 font-mono">
              {telemetry.last_confirmed_presence || 'Not detected yet'}
            </span>
          </div>
        </div>

        {/* Right: Absence Threshold Settings & Video Stream */}
        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-card space-y-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Sliders className="h-5 w-5 text-primary" /> Absence Alert Limit
              </h3>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-lg bg-orange-50 text-primary border border-orange-200">
                {absenceThresholdMin} min
              </span>
            </div>

            <p className="text-xs text-slate-500 mb-3">
              Auto-generates a continuous absence alarm when an employee is absent from their post beyond this limit.
            </p>

            <div className="grid grid-cols-4 gap-2">
              {[5, 10, 15, 30].map((m) => (
                <button
                  key={m}
                  onClick={() => handleSaveThreshold(m)}
                  disabled={savingThreshold}
                  className={`py-2 rounded-xl text-xs font-bold transition-all ${
                    absenceThresholdMin === m
                      ? 'bg-primary text-white shadow-brand'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  {m}m
                </button>
              ))}
            </div>
          </div>

          {/* Quick Workstation Live Feed */}
          <div className="rounded-xl overflow-hidden bg-slate-900 aspect-video relative flex items-center justify-center border border-slate-800">
            <img
              src={`${BACKEND_URL}/api/camera/workstation/stream`}
              alt="Workstation Camera"
              className="w-full h-full object-cover"
              onError={(e) => {
                // If stream is offline
              }}
            />
            <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/60 backdrop-blur-xs text-[10px] font-mono text-emerald-400">
              Station {selectedWsId || 1} • ROI Active
            </div>
          </div>
        </div>
      </div>

      {/* Discrete Presence Intervals Breakdown Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-slate-900">Discrete Presence Intervals</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Completed non-overlapping intervals contributing to today's active workstation duration
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => selectedWsId && selectedEmpId && loadIntervals(selectedWsId, selectedEmpId)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 hover:border-primary text-xs font-semibold text-slate-600 hover:text-primary transition-all flex items-center gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
            <button
              onClick={handleResetDailyTime}
              className="px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-600 border border-rose-200 text-xs font-semibold transition-all flex items-center gap-1.5"
            >
              <Trash2 className="h-3.5 w-3.5" /> Reset Today
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-100 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                <th className="px-6 py-3.5">Interval ID</th>
                <th className="px-6 py-3.5">Start Time</th>
                <th className="px-6 py-3.5">End Time</th>
                <th className="px-6 py-3.5">Duration</th>
                <th className="px-6 py-3.5">Status / Quality</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm text-slate-700">
              {intervals.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-10 text-slate-400">
                    <Timer className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <span>No completed presence intervals recorded for this session today yet</span>
                  </td>
                </tr>
              ) : (
                intervals.map((inv) => {
                  const durSec = inv.duration_seconds || 0;
                  const mins = Math.floor(durSec / 60);
                  const secs = Math.floor(durSec % 60);
                  const formattedDur = `${mins}m ${secs}s`;

                  return (
                    <tr key={inv.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-3.5 font-mono text-xs text-slate-500">#{inv.id}</td>
                      <td className="px-6 py-3.5 font-medium text-slate-900">
                        {inv.start_time ? format(new Date(inv.start_time), 'p') : '--'}
                      </td>
                      <td className="px-6 py-3.5 font-medium text-slate-900">
                        {inv.end_time ? format(new Date(inv.end_time), 'p') : 'Active...'}
                      </td>
                      <td className="px-6 py-3.5 font-mono font-bold text-primary">{formattedDur}</td>
                      <td className="px-6 py-3.5">
                        {inv.is_uncertain ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            <AlertTriangle className="h-3 w-3" /> Outage Adjusted
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle2 className="h-3 w-3" /> Continuous
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-3.5 text-right">
                        <button
                          onClick={() => {
                            setEditingInterval(inv);
                            setCorrectionDuration(String(inv.duration_seconds || ''));
                            setCorrectionNote('');
                          }}
                          className="px-2.5 py-1 rounded-lg text-xs font-semibold text-slate-600 hover:text-primary hover:bg-slate-100 transition-all inline-flex items-center gap-1"
                        >
                          <Edit2 className="h-3.5 w-3.5" /> Adjust
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Break Management Modal */}
      <AnimatePresence>
        {breakModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setBreakModalOpen(false)}
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
                  <Coffee className="h-5 w-5 text-amber-500" /> Start Scheduled Break
                </h3>
                <button
                  onClick={() => setBreakModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Break Type</label>
                  <select
                    value={breakType}
                    onChange={(e) => setBreakType(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  >
                    <option value="Lunch Break">Lunch Break</option>
                    <option value="Tea Break">Tea Break</option>
                    <option value="Rest Break">Rest Break</option>
                    <option value="Approved Leave">Approved Leave</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Notes</label>
                  <input
                    type="text"
                    value={breakNotes}
                    onChange={(e) => setBreakNotes(e.target.value)}
                    placeholder="e.g. Standard 30 min lunch"
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setBreakModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleStartBreak}
                    disabled={breakLoading}
                    className="px-5 py-2 rounded-xl text-xs font-semibold bg-amber-500 hover:bg-amber-600 text-white shadow-brand"
                  >
                    {breakLoading ? 'Activating...' : 'Begin Break'}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Interval Adjustment Modal */}
      <AnimatePresence>
        {editingInterval && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setEditingInterval(null)}
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
                  <Edit2 className="h-5 w-5 text-primary" /> Adjust Presence Interval #{editingInterval.id}
                </h3>
                <button
                  onClick={() => setEditingInterval(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleCorrectionSubmit} className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">
                    Duration (in Seconds)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={correctionDuration}
                    onChange={(e) => setCorrectionDuration(e.target.value)}
                    required
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                  <span className="text-[11px] text-slate-400 mt-1 block">
                    Approx {Math.round(parseFloat(correctionDuration || '0') / 60)} minutes
                  </span>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Reason / Audit Note</label>
                  <input
                    type="text"
                    value={correctionNote}
                    onChange={(e) => setCorrectionNote(e.target.value)}
                    required
                    placeholder="e.g. Verified employee was at post during camera outage"
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setEditingInterval(null)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-hover text-white shadow-brand"
                  >
                    Save Correction
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

'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UserCheck,
  Calendar,
  Search,
  Plus,
  RefreshCw,
  Video,
  Clock,
  ShieldCheck,
  AlertTriangle,
  User,
  Users,
  Camera,
  Layers,
  ArrowRight,
  X,
  Play,
  Square,
} from 'lucide-react';
import {
  BACKEND_URL,
  getAttendance,
  getEmployees,
  manualAttendanceCheckIn,
  startCamera,
  stopCamera,
  getCameraStatus,
} from '@/lib/attendanceApi';
import { toast } from '@/components/feedback/Toast';
import { AttendanceNotifier } from '@/components/attendance/AttendanceNotifier';

export default function AttendancePage() {
  const [records, setRecords] = useState<any[]>([]);
  const [filtered, setFiltered] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [selectedDate, setSelectedDate] = useState<string>(format(new Date(), 'yyyy-MM-dd'));
  const [dateFilterType, setDateFilterType] = useState<'today' | 'all' | 'custom'>('today');
  const [loading, setLoading] = useState(false);

  // Manual Check-In Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [manualEmpId, setManualEmpId] = useState('');
  const [manualDate, setManualDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [manualNotes, setManualNotes] = useState('Manual attendance check-in');
  const [submitting, setSubmitting] = useState(false);

  // Live Camera Preview
  const [isCameraRunning, setIsCameraRunning] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [streamKey, setStreamKey] = useState<number>(Date.now());

  useEffect(() => {
    loadEmployees();
    checkCameraStatus();
  }, []);

  useEffect(() => {
    loadAttendance();
  }, [selectedDate, dateFilterType]);

  const loadEmployees = async () => {
    try {
      const data = await getEmployees();
      setEmployees(data || []);
      if (data && data.length > 0 && !manualEmpId) {
        setManualEmpId(data[0].employee_id);
      }
    } catch (e) {
      console.error('Error loading employees:', e);
    }
  };

  const checkCameraStatus = async () => {
    try {
      const res = await getCameraStatus();
      setIsCameraRunning(res?.status === 'running');
    } catch {
      // fallback
    }
  };

  const loadAttendance = async () => {
    setLoading(true);
    try {
      const dateParam = dateFilterType === 'all' ? undefined : selectedDate;
      const data = await getAttendance(dateParam);
      setRecords(data || []);
      applyFilter(data || [], search);
    } catch (e: any) {
      toast.error('Failed to load attendance', e.message);
    } finally {
      setLoading(false);
    }
  };

  const applyFilter = (data: any[], searchTerm: string) => {
    const s = searchTerm.toLowerCase();
    const result = data.filter(
      (r) =>
        r.employee_id?.toLowerCase().includes(s) ||
        r.name?.toLowerCase().includes(s) ||
        (r.notes && r.notes.toLowerCase().includes(s))
    );
    setFiltered(result);
  };

  useEffect(() => {
    applyFilter(records, search);
  }, [search, records]);

  const handleManualCheckIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualEmpId) {
      toast.error('Please select an employee');
      return;
    }
    setSubmitting(true);
    try {
      await manualAttendanceCheckIn(
        manualEmpId,
        'supervisor',
        manualNotes,
        manualDate
      );
      toast.success(`Manual attendance recorded for ${manualEmpId}`);
      setIsModalOpen(false);
      loadAttendance();
    } catch (err: any) {
      toast.error(err.message || 'Manual check-in failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleCamera = async () => {
    setCameraLoading(true);
    try {
      if (isCameraRunning) {
        await stopCamera();
        setIsCameraRunning(false);
        toast.info('Attendance camera stopped');
      } else {
        await startCamera();
        setIsCameraRunning(true);
        setStreamKey(Date.now());
        toast.success('Attendance camera started');
      }
    } catch (err: any) {
      toast.error(err.message || 'Camera operation failed');
    } finally {
      setCameraLoading(false);
    }
  };

  const totalPresent = records.filter((r) => !r.is_duplicate).length;
  const verifiedCount = records.filter((r) => r.status === 'VERIFIED').length;
  const manualCount = records.filter((r) => r.status === 'MANUAL_CORRECTION').length;

  return (
    <div className="space-y-6">
      <AttendanceNotifier />

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
            <ShieldCheck className="h-4 w-4" />
            <span>Biometric AI Verification</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
            Attendance & Face Check-In
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Automated facial recognition check-in with anti-spoofing and multi-frame verification
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={handleToggleCamera}
            disabled={cameraLoading}
            className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
              isCameraRunning
                ? 'bg-rose-50 text-rose-600 border border-rose-200 hover:bg-rose-100'
                : 'bg-emerald-50 text-emerald-600 border border-emerald-200 hover:bg-emerald-100'
            }`}
          >
            {isCameraRunning ? (
              <>
                <Square className="h-4 w-4 fill-current" /> Stop Camera
              </>
            ) : (
              <>
                <Play className="h-4 w-4 fill-current" /> Start AI Camera
              </>
            )}
          </button>

          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-primary hover:bg-primary-hover text-white shadow-brand transition-all cursor-pointer"
          >
            <Plus className="h-4 w-4" /> Manual Check-In
          </button>

          <Link
            href="/dashboard/attendance/enrollment"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <User className="h-4 w-4" /> Face Enrollment
          </Link>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Present Today
            </span>
            <div className="h-9 w-9 rounded-xl bg-orange-50 text-primary flex items-center justify-center">
              <UserCheck className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{totalPresent}</div>
          <p className="text-xs text-slate-400 mt-1">Unique active employee check-ins</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              AI Face Verified
            </span>
            <div className="h-9 w-9 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{verifiedCount}</div>
          <p className="text-xs text-emerald-600 mt-1 font-medium">Liveness & confidence confirmed</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Manual Corrections
            </span>
            <div className="h-9 w-9 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
              <Clock className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{manualCount}</div>
          <p className="text-xs text-slate-400 mt-1">Supervisor manual check-ins</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              AI Camera Device
            </span>
            <div
              className={`h-9 w-9 rounded-xl flex items-center justify-center ${
                isCameraRunning ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'
              }`}
            >
              <Camera className="h-5 w-5" />
            </div>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                isCameraRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'
              }`}
            />
            <span className="text-base font-bold text-slate-900">
              {isCameraRunning ? 'Online & Streaming' : 'Offline / Standby'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">DirectShow 640x480 MJPG feed</p>
        </div>
      </div>

      {/* Live Camera Stream Feed (Collapsible / Active) */}
      {isCameraRunning && (
        <div className="bg-slate-900 rounded-2xl p-5 border border-slate-800 text-white overflow-hidden shadow-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-red-500 animate-ping" />
              <span className="text-sm font-bold tracking-wide">Live Biometric Recognition Stream</span>
            </div>
            <span className="text-xs font-mono text-slate-400">YOLOv8 + DeepSORT Active</span>
          </div>
          <div className="relative rounded-xl overflow-hidden bg-black flex items-center justify-center aspect-video max-h-[380px] w-full border border-slate-800">
            <img
              src={`${BACKEND_URL}/api/camera/stream?t=${streamKey}`}
              alt="Live Attendance Feed"
              className="w-full h-full object-contain"
              onError={() => {
                // If stream cannot be loaded
              }}
            />
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white rounded-2xl p-4 border border-slate-100 shadow-card flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setDateFilterType('today')}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              dateFilterType === 'today'
                ? 'bg-primary text-white shadow-xs'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            Today
          </button>
          <button
            onClick={() => setDateFilterType('all')}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              dateFilterType === 'all'
                ? 'bg-primary text-white shadow-xs'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            All History
          </button>
          <button
            onClick={() => setDateFilterType('custom')}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              dateFilterType === 'custom'
                ? 'bg-primary text-white shadow-xs'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            Custom Date
          </button>

          {dateFilterType === 'custom' && (
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-medium text-slate-700 bg-white outline-none focus:border-primary"
            />
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name or ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-primary transition-all"
            />
          </div>
          <button
            onClick={loadAttendance}
            disabled={loading}
            className="p-2 rounded-xl border border-slate-200 hover:border-primary text-slate-500 hover:text-primary transition-all"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Attendance Records Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">Attendance Check-In Logs</h3>
          <span className="text-xs text-slate-500 font-medium">{filtered.length} entries shown</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-100 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                <th className="px-6 py-3.5">Employee</th>
                <th className="px-6 py-3.5">Date & Time</th>
                <th className="px-6 py-3.5">Confidence</th>
                <th className="px-6 py-3.5">Status</th>
                <th className="px-6 py-3.5">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm text-slate-700">
              {loading && filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <RefreshCw className="h-6 w-6 animate-spin text-primary" />
                      <span>Loading attendance records...</span>
                    </div>
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <UserCheck className="h-8 w-8 text-slate-300" />
                      <span className="font-medium">No attendance records found for this period</span>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map((item) => {
                  const isVerified = item.status === 'VERIFIED';
                  const isManual = item.status === 'MANUAL_CORRECTION';
                  const isLivenessFailed = item.status === 'LIVENESS_FAILED';

                  return (
                    <tr key={item.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-slate-100 text-slate-600 font-bold text-xs flex items-center justify-center border border-slate-200">
                            {item.name?.charAt(0)?.toUpperCase() || 'E'}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900">{item.name}</div>
                            <div className="text-xs font-mono text-slate-500">{item.employee_id}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-3.5">
                        <div className="font-medium text-slate-800">
                          {item.timestamp ? format(new Date(item.timestamp), 'PP') : item.date}
                        </div>
                        <div className="text-xs text-slate-400">
                          {item.timestamp ? format(new Date(item.timestamp), 'p') : '--'}
                        </div>
                      </td>
                      <td className="px-6 py-3.5">
                        {item.confidence ? (
                          <div className="flex items-center gap-1.5 font-mono text-xs font-semibold text-slate-800">
                            <div className="w-12 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="bg-emerald-500 h-1.5 rounded-full"
                                style={{ width: `${Math.min(100, Math.round(item.confidence * 100))}%` }}
                              />
                            </div>
                            <span>{Math.round(item.confidence * 100)}%</span>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">Manual</span>
                        )}
                      </td>
                      <td className="px-6 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                            isVerified
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : isManual
                              ? 'bg-blue-50 text-blue-700 border border-blue-200'
                              : isLivenessFailed
                              ? 'bg-rose-50 text-rose-700 border border-rose-200'
                              : 'bg-amber-50 text-amber-700 border border-amber-200'
                          }`}
                        >
                          {isVerified ? (
                            <ShieldCheck className="h-3 w-3" />
                          ) : (
                            <Clock className="h-3 w-3" />
                          )}
                          {item.status || 'VERIFIED'}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-xs text-slate-500 max-w-[200px] truncate">
                        {item.notes || 'Biometric check-in verified'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Manual Check-In Modal */}
      <AnimatePresence>
        {isModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsModalOpen(false)}
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-md bg-white rounded-2xl p-6 shadow-2xl border border-slate-100 z-10"
            >
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <h3 className="text-lg font-bold text-slate-900">Manual Attendance Check-In</h3>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleManualCheckIn} className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">
                    Select Employee
                  </label>
                  <select
                    value={manualEmpId}
                    onChange={(e) => setManualEmpId(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  >
                    {employees.map((emp) => (
                      <option key={emp.employee_id} value={emp.employee_id}>
                        {emp.name} ({emp.employee_id}) - {emp.shift_name || 'General Shift'}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Date</label>
                  <input
                    type="date"
                    value={manualDate}
                    onChange={(e) => setManualDate(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 mb-1 block">Notes / Reason</label>
                  <input
                    type="text"
                    value={manualNotes}
                    onChange={(e) => setManualNotes(e.target.value)}
                    placeholder="e.g. Camera unavailable / Authorized manual override"
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white text-slate-800 focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-5 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-hover text-white shadow-brand"
                  >
                    {submitting ? 'Saving...' : 'Record Attendance'}
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

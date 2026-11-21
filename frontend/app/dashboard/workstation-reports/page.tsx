'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import {
  FileText,
  Filter,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Briefcase,
  Moon,
  Sun,
  User,
  MapPin,
  Calendar,
  Layers,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import { getDailyReport, getWorkstations, getShifts } from '@/lib/attendanceApi';
import { toast } from '@/components/feedback/Toast';

export default function WorkstationReportsPage() {
  const [reportData, setReportData] = useState<any>({
    date: '',
    total_employees: 0,
    present_count: 0,
    total_workstation_hours: '0m',
    records: [],
  });
  const [workstations, setWorkstations] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [selectedShift, setSelectedShift] = useState<string>('ALL');
  const [selectedWs, setSelectedWs] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    setMounted(true);
    const today = format(new Date(), 'yyyy-MM-dd');
    setSelectedDate(today);
    getWorkstations().then(setWorkstations).catch(() => {});
    getShifts().then(setShifts).catch(() => {});
  }, []);

  const loadReport = async () => {
    setLoading(true);
    const dateQuery = selectedDate || format(new Date(), 'yyyy-MM-dd');
    try {
      const data = await getDailyReport({
        date: dateQuery,
        shift: selectedShift !== 'ALL' ? selectedShift : undefined,
        workstation_id: selectedWs !== 'ALL' ? Number(selectedWs) : undefined,
      });
      setReportData(data || { records: [] });
    } catch (err: any) {
      toast.error('Reports load error', err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (mounted && selectedDate) {
      loadReport();
    }
  }, [mounted, selectedDate, selectedShift, selectedWs]);

  const filteredRecords = (reportData?.records || []).filter((r: any) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.employee_name?.toLowerCase().includes(q) ||
      r.employee_id?.toLowerCase().includes(q) ||
      r.assigned_shift?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
            <FileText className="h-4 w-4" />
            <span>Shift-Wise Productivity Audit</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
            Workstation Presence & Hours Reports
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Day-wise & shift-wise cumulative active workstation hours adhering strictly to individual employee shifts
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Link
            href="/dashboard/workstations"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-slate-200 hover:border-primary text-slate-700 hover:text-primary transition-all shadow-xs"
          >
            <Clock className="h-4 w-4 text-primary" /> Live Workstations
          </Link>
          <button
            onClick={loadReport}
            disabled={loading}
            className="p-2.5 rounded-xl border border-slate-200 hover:border-primary text-slate-500 hover:text-primary transition-all"
            title="Refresh Report"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Roster
            </span>
            <div className="h-9 w-9 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
              <User className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {reportData.total_employees || 0}
          </div>
          <p className="text-xs text-slate-400 mt-1">Configured for active shift</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Present Today
            </span>
            <div className="h-9 w-9 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 mt-2">
            {reportData.present_count || 0}
          </div>
          <p className="text-xs text-slate-400 mt-1">Verified biometric attendance</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Workstation Time
            </span>
            <div className="h-9 w-9 rounded-xl bg-orange-50 text-primary flex items-center justify-center">
              <Clock className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold font-mono text-slate-900 mt-2">
            {reportData.total_workstation_hours || '0m'}
          </div>
          <p className="text-xs text-slate-400 mt-1">Cumulative desk presence</p>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Shift Attendance Rate
            </span>
            <div className="h-9 w-9 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center">
              <TrendingUp className="h-5 w-5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {reportData.total_employees
              ? `${Math.round(
                  ((reportData.present_count || 0) / reportData.total_employees) * 100
                )}%`
              : '0%'}
          </div>
          <p className="text-xs text-slate-400 mt-1">Roster participation ratio</p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white rounded-2xl p-4 border border-slate-100 shadow-card flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <div>
            <label className="text-[11px] font-bold uppercase text-slate-400 block mb-1">
              Select Date
            </label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs bg-white text-slate-800 focus:outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="text-[11px] font-bold uppercase text-slate-400 block mb-1">
              Filter Shift
            </label>
            <select
              value={selectedShift}
              onChange={(e) => setSelectedShift(e.target.value)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs bg-white text-slate-800 focus:outline-none focus:border-primary"
            >
              <option value="ALL">All Shifts</option>
              {shifts.map((s) => (
                <option key={s.id} value={s.shift_name}>
                  {s.shift_name} ({s.timing})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] font-bold uppercase text-slate-400 block mb-1">
              Filter Workstation
            </label>
            <select
              value={selectedWs}
              onChange={(e) => setSelectedWs(e.target.value)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs bg-white text-slate-800 focus:outline-none focus:border-primary"
            >
              <option value="ALL">All Stations</option>
              {workstations.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.code} ({w.name})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="self-end md:self-auto w-full md:w-64">
          <label className="text-[11px] font-bold uppercase text-slate-400 block mb-1">
            Search Employee
          </label>
          <input
            type="text"
            placeholder="Search by name, ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-primary"
          />
        </div>
      </div>

      {/* Report Data Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">Shift-Wise Employee Workstation Time</h3>
          <span className="text-xs text-slate-500 font-medium">
            {filteredRecords.length} employees listed
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-100 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                <th className="px-6 py-3.5">Employee</th>
                <th className="px-6 py-3.5">Assigned Shift</th>
                <th className="px-6 py-3.5">Attendance</th>
                <th className="px-6 py-3.5">Active Desk Time</th>
                <th className="px-6 py-3.5">Break Taken</th>
                <th className="px-6 py-3.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm text-slate-700">
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    <RefreshCw className="h-6 w-6 animate-spin text-primary mx-auto mb-2" />
                    <span>Compiling daily workstation presence report...</span>
                  </td>
                </tr>
              ) : filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    <FileText className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <span className="font-medium">No matching records found for this shift/date</span>
                  </td>
                </tr>
              ) : (
                filteredRecords.map((r: any) => {
                  const isPresent = r.is_present;
                  return (
                    <tr key={r.employee_id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-3.5">
                        <div className="font-semibold text-slate-900">{r.employee_name}</div>
                        <div className="text-xs font-mono text-slate-500">{r.employee_id}</div>
                      </td>
                      <td className="px-6 py-3.5">
                        <div className="font-medium text-slate-800">{r.assigned_shift || 'General Shift'}</div>
                        <div className="text-xs text-slate-400">{r.shift_timing || '09:00 - 18:00'}</div>
                      </td>
                      <td className="px-6 py-3.5">
                        {isPresent ? (
                          <div className="text-xs font-medium text-emerald-700">
                            Check-in: {r.check_in_time ? format(new Date(r.check_in_time), 'p') : 'Present'}
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">Not checked in</span>
                        )}
                      </td>
                      <td className="px-6 py-3.5 font-mono font-bold text-primary">
                        {r.active_time_formatted || '00h 00m 00s'}
                      </td>
                      <td className="px-6 py-3.5 text-xs text-slate-600 font-mono">
                        {r.break_duration_formatted || '0m'}
                      </td>
                      <td className="px-6 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                            isPresent
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-slate-100 text-slate-500 border border-slate-200'
                          }`}
                        >
                          {isPresent ? (
                            <>
                              <CheckCircle2 className="h-3 w-3" /> Present
                            </>
                          ) : (
                            <>
                              <XCircle className="h-3 w-3" /> Absent
                            </>
                          )}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

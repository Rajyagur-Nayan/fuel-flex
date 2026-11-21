'use client';

import { useEffect, useRef } from 'react';
import { useAttendanceWebSocket } from '@/hooks/useAttendanceWebSocket';
import { toast } from '@/components/feedback/Toast';

export function AttendanceNotifier() {
  const { lastMessage } = useAttendanceWebSocket();
  const lastKeyRef = useRef<string>('');
  const lastTimeRef = useRef<number>(0);

  useEffect(() => {
    if (!lastMessage) return;

    const now = Date.now();

    if (
      lastMessage.type === 'attendance' &&
      (lastMessage.status === 'CONFIRMED' || !lastMessage.status)
    ) {
      const key = `att_${lastMessage.employee_id}_${lastMessage.date || ''}_${lastMessage.is_duplicate}`;
      // Prevent repeated toasts for the same confirmation within 3 seconds
      if (key === lastKeyRef.current && now - lastTimeRef.current < 3000) {
        return;
      }
      lastKeyRef.current = key;
      lastTimeRef.current = now;

      const name = lastMessage.employee_name || `Employee ${lastMessage.employee_id}`;
      const time = lastMessage.timestamp || new Date().toLocaleTimeString();
      const conf = lastMessage.confidence
        ? `${Math.round(lastMessage.confidence * 100)}%`
        : 'Verified';

      if (lastMessage.is_duplicate) {
        toast.info(
          `Duplicate Check-in: ${name} (${lastMessage.employee_id} already marked present today)`
        );
      } else {
        toast.success(
          `Attendance Verified: ${name} (ID: ${lastMessage.employee_id} • ${time} • ${conf})`
        );
      }
    } else if (lastMessage.type === 'liveness_failed') {
      const key = `liveness_${lastMessage.track_id || 0}`;
      if (key === lastKeyRef.current && now - lastTimeRef.current < 5000) {
        return;
      }
      lastKeyRef.current = key;
      lastTimeRef.current = now;

      toast.error('Anti-Spoofing Alert: Static photo or screen detected. Attendance rejected.');
    }
  }, [lastMessage]);

  return null;
}

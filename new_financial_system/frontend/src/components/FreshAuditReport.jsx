import React, { useState, useEffect } from 'react';

const FreshAuditReport = () => {
  const [transactions, setTransactions] = useState([]);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [classFilter, setClassFilter] = useState('');
  
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/audit/system')
      .then(res => res.json())
      .then(data => {
        setTransactions(data.transactions || []);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const filteredTransactions = transactions.filter(t => {
    let matchesDate = true;
    let matchesClass = true;
    
    if (startDate) {
      matchesDate = matchesDate && new Date(t.date_created) >= new Date(startDate);
    }
    if (endDate) {
      matchesDate = matchesDate && new Date(t.date_created) <= new Date(endDate);
    }
    if (classFilter) {
      matchesClass = t.class_name && t.class_name.toLowerCase().includes(classFilter.toLowerCase());
    }
    
    return matchesDate && matchesClass;
  });

  return (
    <div className="p-8 max-w-6xl mx-auto font-sans text-gray-800 bg-white min-h-screen">
      <div className="print:hidden mb-8 flex flex-col md:flex-row justify-between items-start md:items-center border-b pb-6 border-gray-100">
        <h1 className="text-3xl font-light mb-4 md:mb-0">System Audit Report</h1>
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex flex-col">
            <label className="text-xs text-gray-500 mb-1">Start Date</label>
            <input type="date" className="border px-3 py-1.5 rounded text-sm focus:outline-none focus:border-blue-400" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-500 mb-1">End Date</label>
            <input type="date" className="border px-3 py-1.5 rounded text-sm focus:outline-none focus:border-blue-400" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-500 mb-1">Class Filter</label>
            <input type="text" placeholder="e.g. Grade 1" className="border px-3 py-1.5 rounded text-sm focus:outline-none focus:border-blue-400" value={classFilter} onChange={e => setClassFilter(e.target.value)} />
          </div>
          <button onClick={() => window.print()} className="mt-5 bg-gray-800 text-white px-4 py-1.5 rounded text-sm hover:bg-gray-900 transition">
            Print Report
          </button>
        </div>
      </div>

      <div className="hidden print:block mb-6 text-center">
        <h1 className="text-2xl font-bold">Official Audit Report</h1>
        <p className="text-sm text-gray-500">Generated on {new Date().toLocaleDateString()}</p>
      </div>

      {loading ? (
        <div className="text-gray-500 flex justify-center py-12">Loading data...</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-200">
                <th className="py-3 px-4 font-medium text-sm text-gray-600">Date</th>
                <th className="py-3 px-4 font-medium text-sm text-gray-600">Student</th>
                <th className="py-3 px-4 font-medium text-sm text-gray-600">Class</th>
                <th className="py-3 px-4 font-medium text-sm text-gray-600">Type</th>
                <th className="py-3 px-4 font-medium text-sm text-gray-600">Reason</th>
                <th className="py-3 px-4 font-medium text-sm text-gray-600 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {filteredTransactions.length === 0 ? (
                <tr>
                  <td colSpan="6" className="py-6 text-center text-gray-400 text-sm">No transactions found</td>
                </tr>
              ) : (
                filteredTransactions.map((t) => (
                  <tr key={t.id} className="border-b border-gray-100 hover:bg-gray-50 transition print:hover:bg-white">
                    <td className="py-3 px-4 text-sm">{new Date(t.date_created).toLocaleDateString()}</td>
                    <td className="py-3 px-4 text-sm font-medium">{t.student_name || `ID: ${t.student_id}`}</td>
                    <td className="py-3 px-4 text-sm">{t.class_name || '-'}</td>
                    <td className="py-3 px-4 text-sm capitalize">{t.transaction_type.replace('_', ' ')}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">{t.reason || '-'}</td>
                    <td className={`py-3 px-4 text-sm text-right font-medium ${t.amount < 0 ? 'text-green-600' : 'text-gray-900'}`}>
                      ${Math.abs(t.amount).toFixed(2)} {t.amount < 0 ? '(Cr)' : '(Dr)'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default FreshAuditReport;

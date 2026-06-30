import React, { useState, useEffect } from 'react';

const StudentLedgerView = ({ studentId }) => {
  const [ledgerData, setLedgerData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchLedger = async () => {
      try {
        const response = await fetch(`/api/ledger/${studentId}`, {
          headers: {
            'X-User-Role': 'student',
            'X-User-Id': studentId
          }
        });
        if (!response.ok) throw new Error('Failed to fetch ledger');
        const data = await response.json();
        setLedgerData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchLedger();
  }, [studentId]);

  if (loading) return <div className="p-8 text-gray-500 text-sm">Loading ledger...</div>;
  if (error) return <div className="p-8 text-red-500 text-sm">{error}</div>;

  return (
    <div className="max-w-4xl mx-auto p-6 bg-white rounded-xl shadow-sm border border-gray-100 mt-8">
      <header className="mb-8 border-b border-gray-100 pb-6">
        <h1 className="text-2xl font-semibold text-gray-800">Financial Ledger</h1>
        <p className="text-gray-500 text-sm mt-1">{ledgerData.student.name} • Class {ledgerData.student.class_id}</p>
      </header>

      <div className="grid grid-cols-2 gap-6 mb-8">
        <div className="p-6 bg-gray-50 rounded-lg border border-gray-100">
          <p className="text-sm text-gray-500 font-medium uppercase tracking-wider mb-1">Total Balance Due</p>
          <p className="text-3xl font-light text-gray-900">₹{ledgerData.total_balance_due.toFixed(2)}</p>
        </div>
        <div className="p-6 bg-gray-50 rounded-lg border border-gray-100">
          <p className="text-sm text-gray-500 font-medium uppercase tracking-wider mb-1">Next Payment Date</p>
          <p className="text-xl font-light text-gray-700 mt-2">1st of Next Month</p>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 border-b border-gray-200 text-gray-600 font-medium">
            <tr>
              <th className="px-6 py-4">Date</th>
              <th className="px-6 py-4">Description</th>
              <th className="px-6 py-4">Type</th>
              <th className="px-6 py-4 text-right">Amount</th>
              <th className="px-6 py-4 text-right">Balance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {ledgerData.ledger.map((tx) => (
              <tr key={tx.id} className="hover:bg-gray-50/50 transition-colors">
                <td className="px-6 py-4 text-gray-600">
                  {new Date(tx.date_created).toLocaleDateString()}
                </td>
                <td className="px-6 py-4 text-gray-800">{tx.description || '-'}</td>
                <td className="px-6 py-4">
                  <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                    tx.transaction_type === 'fee_generation' ? 'bg-orange-50 text-orange-700' :
                    tx.transaction_type === 'payment' ? 'bg-green-50 text-green-700' :
                    'bg-blue-50 text-blue-700'
                  }`}>
                    {tx.transaction_type.replace('_', ' ')}
                  </span>
                </td>
                <td className={`px-6 py-4 text-right font-medium ${tx.amount < 0 ? 'text-green-600' : 'text-gray-900'}`}>
                  {tx.amount < 0 ? '-' : ''}₹{Math.abs(tx.amount).toFixed(2)}
                </td>
                <td className="px-6 py-4 text-right text-gray-600 font-medium">
                  ₹{tx.running_balance.toFixed(2)}
                </td>
              </tr>
            ))}
            {ledgerData.ledger.length === 0 && (
              <tr>
                <td colSpan="5" className="px-6 py-8 text-center text-gray-500">
                  No transactions found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default StudentLedgerView;

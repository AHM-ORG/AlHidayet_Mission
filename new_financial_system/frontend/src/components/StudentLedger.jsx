import React, { useState, useEffect } from 'react';

const StudentLedger = ({ studentId }) => {
  const [ledger, setLedger] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // If using routing, studentId might come from useParams()
  // For this component, we'll assume it's passed as a prop, or we can use a hardcoded fallback for demonstration
  const idToFetch = studentId || 1; 

  useEffect(() => {
    fetch(`/api/ledger/${idToFetch}`)
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch ledger');
        return res.json();
      })
      .then(data => {
        setLedger(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [idToFetch]);

  if (loading) return <div className="p-8 text-gray-500">Loading ledger...</div>;
  if (error) return <div className="p-8 text-red-500">{error}</div>;
  if (!ledger || !ledger.student) return <div className="p-8 text-gray-500">Student not found.</div>;

  const { student, transactions } = ledger;

  return (
    <div className="p-8 max-w-4xl mx-auto font-sans text-gray-800 bg-white min-h-screen">
      <div className="mb-8 pb-6 border-b border-gray-100 flex flex-col md:flex-row justify-between items-start md:items-end">
        <div>
          <h1 className="text-3xl font-light mb-2">{student.name}'s Ledger</h1>
          <p className="text-sm text-gray-500">Class: {student.class || 'N/A'} | ID: {student.id}</p>
        </div>
        <div className="mt-4 md:mt-0 text-right">
          <p className="text-sm text-gray-500 uppercase tracking-wide mb-1">Current Balance</p>
          <p className={`text-3xl font-medium ${student.current_balance > 0 ? 'text-red-600' : 'text-green-600'}`}>
            ${student.current_balance.toFixed(2)}
          </p>
        </div>
      </div>

      <h2 className="text-xl font-medium mb-4">Transaction History</h2>
      
      <div className="bg-white border border-gray-100 rounded shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="py-3 px-4 font-medium text-sm text-gray-600 w-32">Date</th>
              <th className="py-3 px-4 font-medium text-sm text-gray-600 w-40">Type</th>
              <th className="py-3 px-4 font-medium text-sm text-gray-600">Details</th>
              <th className="py-3 px-4 font-medium text-sm text-gray-600 text-right w-32">Amount</th>
            </tr>
          </thead>
          <tbody>
            {transactions.length === 0 ? (
              <tr>
                <td colSpan="4" className="py-8 text-center text-gray-400 text-sm">No transactions on record.</td>
              </tr>
            ) : (
              transactions.map((t, index) => (
                <tr key={t.id} className={`border-b border-gray-50 hover:bg-gray-50 transition ${index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}>
                  <td className="py-4 px-4 text-sm text-gray-600 whitespace-nowrap">
                    {new Date(t.date_created).toLocaleDateString()}
                  </td>
                  <td className="py-4 px-4 text-sm capitalize font-medium text-gray-700">
                    {t.transaction_type.replace('_', ' ')}
                  </td>
                  <td className="py-4 px-4 text-sm text-gray-600">
                    {t.reason || 'No specific reason provided'}
                  </td>
                  <td className={`py-4 px-4 text-sm text-right font-medium ${t.amount < 0 ? 'text-green-600' : 'text-gray-900'}`}>
                    {t.amount < 0 ? '-' : '+'}${Math.abs(t.amount).toFixed(2)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      
      <div className="mt-8 text-sm text-gray-400 text-center print:hidden">
        End of ledger for {student.name}.
      </div>
    </div>
  );
};

export default StudentLedger;

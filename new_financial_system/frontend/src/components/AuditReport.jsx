import React, { useState, useEffect } from 'react';

const AuditReport = () => {
  const [reportType, setReportType] = useState('monthly'); // 'monthly' or 'yearly'
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchAudit = async () => {
      setLoading(true);
      try {
        const response = await fetch(`/api/audit/${reportType}`, {
          headers: { 'X-User-Role': 'admin' }
        });
        if (!response.ok) throw new Error('Failed to fetch audit data');
        const json = await response.json();
        setData(json.audit);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchAudit();
  }, [reportType]);

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="min-h-screen bg-gray-50 print:bg-white print:m-0 print:p-0 font-sans text-gray-900">
      
      {/* 
        NON-PRINTABLE UI: 
        Using print:hidden so this sidebar/nav layout entirely vanishes when printing.
      */}
      <div className="max-w-6xl mx-auto p-8 print:hidden">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-light tracking-tight text-gray-900">Audit Report Generator</h1>
            <p className="text-gray-500 text-sm mt-1">Select timeframe and generate printable A4 reports.</p>
          </div>
          <div className="flex items-center gap-4">
            <select 
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-100 outline-none"
            >
              <option value="monthly">Monthly Rollup</option>
              <option value="yearly">Yearly Rollup</option>
            </select>
            <button 
              onClick={handlePrint}
              className="px-6 py-2 bg-gray-900 hover:bg-gray-800 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              Print Report
            </button>
          </div>
        </div>
      </div>

      {/* 
        PRINTABLE A4 DOCUMENT AREA 
        We use print:block print:w-full print:border-none etc to format it for paper.
      */}
      <div className="max-w-4xl mx-auto bg-white p-12 shadow-sm border border-gray-200 rounded-xl mb-12 
                      print:shadow-none print:border-none print:w-full print:max-w-none print:p-0 print:m-0">
        
        {/* Document Header */}
        <div className="text-center mb-10 border-b-2 border-gray-900 pb-6 print:border-black">
          <h2 className="text-2xl font-bold uppercase tracking-widest text-gray-900 print:text-black">
            Official Audit Report
          </h2>
          <p className="text-sm text-gray-500 mt-2 print:text-black">
            {reportType === 'monthly' ? 'Month-by-Month Aggregation' : 'Annual Aggregation'}
          </p>
          <p className="text-xs text-gray-400 mt-1 print:text-black">
            Generated on: {new Date().toLocaleDateString()}
          </p>
        </div>

        {loading ? (
          <p className="text-center text-gray-500 py-12 print:hidden">Compiling report data...</p>
        ) : error ? (
          <p className="text-center text-red-500 py-12 print:hidden">{error}</p>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-300 print:border-black text-sm uppercase tracking-wider text-gray-700 font-semibold print:text-black">
                <th className="py-3 px-2">{reportType === 'monthly' ? 'Month' : 'Year'}</th>
                <th className="py-3 px-2 text-right">Expected Fees</th>
                <th className="py-3 px-2 text-right">Aid Applied</th>
                <th className="py-3 px-2 text-right">Net Expected</th>
                <th className="py-3 px-2 text-right">Total Collected</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 print:divide-gray-400">
              {data.map((row, index) => (
                <tr key={index} className="text-sm text-gray-800 print:text-black break-inside-avoid">
                  <td className="py-4 px-2 font-medium">{row.month || row.year}</td>
                  <td className="py-4 px-2 text-right">₹{row.expected_fees.toFixed(2)}</td>
                  <td className="py-4 px-2 text-right text-red-600 print:text-black">₹{row.total_aid_applied.toFixed(2)}</td>
                  <td className="py-4 px-2 text-right font-semibold">₹{row.net_expected.toFixed(2)}</td>
                  <td className="py-4 px-2 text-right font-bold text-green-700 print:text-black">₹{row.total_collected.toFixed(2)}</td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr>
                  <td colSpan="5" className="py-8 text-center text-gray-500">No data available for this period.</td>
                </tr>
              )}
            </tbody>
            {data.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-gray-900 print:border-black font-bold text-gray-900 print:text-black text-sm">
                  <td className="py-4 px-2">GRAND TOTAL</td>
                  <td className="py-4 px-2 text-right">
                    ₹{data.reduce((sum, r) => sum + r.expected_fees, 0).toFixed(2)}
                  </td>
                  <td className="py-4 px-2 text-right">
                    ₹{data.reduce((sum, r) => sum + r.total_aid_applied, 0).toFixed(2)}
                  </td>
                  <td className="py-4 px-2 text-right">
                    ₹{data.reduce((sum, r) => sum + r.net_expected, 0).toFixed(2)}
                  </td>
                  <td className="py-4 px-2 text-right">
                    ₹{data.reduce((sum, r) => sum + r.total_collected, 0).toFixed(2)}
                  </td>
                </tr>
              </tfoot>
            )}
          </table>
        )}

        <div className="mt-16 pt-8 border-t border-gray-200 print:border-black flex justify-between text-xs text-gray-500 print:text-black">
          <div>Authorized Signature: _______________________</div>
          <div>Page 1 of 1</div>
        </div>

      </div>
    </div>
  );
};

export default AuditReport;

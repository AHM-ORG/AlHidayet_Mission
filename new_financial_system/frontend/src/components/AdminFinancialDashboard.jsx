import React, { useState } from 'react';
import StudentLedgerView from './StudentLedgerView';

const AdminFinancialDashboard = () => {
  const [searchId, setSearchId] = useState('');
  const [activeStudentId, setActiveStudentId] = useState(null);
  
  const [aidForm, setAidForm] = useState({ amount: '', aid_type: 'flat' });
  const [aidStatus, setAidStatus] = useState('');

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchId) setActiveStudentId(searchId);
  };

  const handleApplyAid = async (e) => {
    e.preventDefault();
    setAidStatus('Applying...');
    try {
      const res = await fetch('/api/aid/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': 'admin'
        },
        body: JSON.stringify({
          student_id: activeStudentId,
          amount: parseFloat(aidForm.amount),
          aid_type: aidForm.aid_type
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setAidStatus('Aid successfully applied!');
      // Typically we would trigger a re-fetch of the ledger here
    } catch (err) {
      setAidStatus(`Error: ${err.message}`);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-8">
      <header className="mb-10 flex justify-between items-end border-b border-gray-100 pb-6">
        <div>
          <h1 className="text-3xl font-light text-gray-900 tracking-tight">Financial Dashboard</h1>
          <p className="text-gray-500 mt-2 text-sm">Manage student accounts, ledgers, and financial aid.</p>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        
        {/* Left Sidebar: Controls */}
        <div className="col-span-1 space-y-6">
          {/* Search Card */}
          <div className="p-6 bg-white rounded-xl shadow-sm border border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">Find Student</h3>
            <form onSubmit={handleSearch} className="space-y-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Student ID</label>
                <input 
                  type="number" 
                  value={searchId}
                  onChange={e => setSearchId(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300 transition-all text-sm"
                  placeholder="Enter ID..."
                  required
                />
              </div>
              <button type="submit" className="w-full py-2 bg-gray-900 hover:bg-gray-800 text-white text-sm font-medium rounded-lg transition-colors">
                View Ledger
              </button>
            </form>
          </div>

          {/* Financial Aid Card */}
          {activeStudentId && (
            <div className="p-6 bg-white rounded-xl shadow-sm border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">Apply Financial Aid</h3>
              <form onSubmit={handleApplyAid} className="space-y-4">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Aid Type</label>
                  <select 
                    value={aidForm.aid_type}
                    onChange={e => setAidForm({...aidForm, aid_type: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 text-sm"
                  >
                    <option value="flat">Flat Amount (₹)</option>
                    <option value="percentage">Percentage (%)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Amount</label>
                  <input 
                    type="number" 
                    step="0.01"
                    value={aidForm.amount}
                    onChange={e => setAidForm({...aidForm, amount: e.target.value})}
                    className="w-full px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 text-sm"
                    placeholder="e.g. 500"
                    required
                  />
                </div>
                <button type="submit" className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
                  Save Aid Settings
                </button>
                {aidStatus && (
                  <p className={`text-xs mt-2 ${aidStatus.includes('Error') ? 'text-red-500' : 'text-green-600'}`}>
                    {aidStatus}
                  </p>
                )}
              </form>
            </div>
          )}
        </div>

        {/* Right Content: Ledger View */}
        <div className="col-span-1 md:col-span-2">
          {activeStudentId ? (
            <StudentLedgerView studentId={activeStudentId} />
          ) : (
            <div className="h-full min-h-[400px] flex items-center justify-center border-2 border-dashed border-gray-200 rounded-xl bg-gray-50/50">
              <p className="text-gray-400 text-sm">Search for a student to view their ledger.</p>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default AdminFinancialDashboard;

import React, { useState } from 'react';

const AdminFeeManager = () => {
  const [classId, setClassId] = useState('');
  const [monthlyFee, setMonthlyFee] = useState('');
  const [readmissionFee, setReadmissionFee] = useState('');
  
  const [studentId, setStudentId] = useState('');
  const [customAmount, setCustomAmount] = useState('');
  const [customReason, setCustomReason] = useState('');
  
  const [aidAmount, setAidAmount] = useState('');
  const [aidReason, setAidReason] = useState('');

  const [activeModal, setActiveModal] = useState(null); // 'customFee' | 'financialAid' | null

  const handleUpdateFees = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/class/update_fees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          class_id: classId,
          monthly_fee_amount: monthlyFee,
          readmission_fee_amount: readmissionFee
        })
      });
      if (res.ok) alert('Fees updated successfully!');
    } catch (err) {
      console.error(err);
      alert('Failed to update fees.');
    }
  };

  const handleGenerateMonthly = async () => {
    if (!classId) return alert('Please enter a Class ID first.');
    try {
      const res = await fetch('/api/fees/generate_monthly', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ class_id: classId })
      });
      const data = await res.json();
      if (res.ok) alert(data.message);
      else alert(data.error);
    } catch (err) {
      console.error(err);
    }
  };

  const handleAddCustomFee = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/fees/add_adhoc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_id: studentId,
          amount: customAmount,
          reason: customReason
        })
      });
      if (res.ok) {
        alert('Custom fee added successfully!');
        setActiveModal(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSetAid = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/aid/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_id: studentId,
          reduction_amount: aidAmount,
          reason: aidReason
        })
      });
      if (res.ok) {
        alert('Financial Aid set successfully!');
        setActiveModal(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto font-sans text-gray-800">
      <h1 className="text-3xl font-light mb-8">Fee Management</h1>
      
      <div className="bg-white p-6 rounded shadow-sm border border-gray-100 mb-8">
        <h2 className="text-xl font-medium mb-4">Class-wise Fees</h2>
        <form onSubmit={handleUpdateFees} className="flex flex-wrap gap-4 items-end">
          <div className="flex flex-col">
            <label className="text-sm text-gray-500 mb-1">Class ID</label>
            <input type="number" className="border px-3 py-2 rounded focus:outline-none focus:border-blue-400" value={classId} onChange={e => setClassId(e.target.value)} required />
          </div>
          <div className="flex flex-col">
            <label className="text-sm text-gray-500 mb-1">Monthly Fee ($)</label>
            <input type="number" className="border px-3 py-2 rounded focus:outline-none focus:border-blue-400" value={monthlyFee} onChange={e => setMonthlyFee(e.target.value)} />
          </div>
          <div className="flex flex-col">
            <label className="text-sm text-gray-500 mb-1">Re-admission Fee ($)</label>
            <input type="number" className="border px-3 py-2 rounded focus:outline-none focus:border-blue-400" value={readmissionFee} onChange={e => setReadmissionFee(e.target.value)} />
          </div>
          <button type="submit" className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 transition">Update</button>
        </form>
        
        <div className="mt-6 pt-6 border-t border-gray-100">
          <button onClick={handleGenerateMonthly} className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 transition">
            Generate Monthly Fees for Class
          </button>
        </div>
      </div>

      <div className="flex gap-4">
        <button onClick={() => setActiveModal('customFee')} className="bg-gray-800 text-white px-6 py-2 rounded hover:bg-gray-900 transition">
          Add Custom Fee / Due
        </button>
        <button onClick={() => setActiveModal('financialAid')} className="bg-purple-600 text-white px-6 py-2 rounded hover:bg-purple-700 transition">
          Set Financial Aid
        </button>
      </div>

      {activeModal === 'customFee' && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex justify-center items-center">
          <div className="bg-white p-6 rounded shadow-lg w-full max-w-md">
            <h2 className="text-xl font-medium mb-4">Add Custom Fee / Previous Due</h2>
            <form onSubmit={handleAddCustomFee} className="flex flex-col gap-4">
              <input type="number" placeholder="Student ID" className="border px-3 py-2 rounded" value={studentId} onChange={e => setStudentId(e.target.value)} required />
              <input type="number" placeholder="Amount" className="border px-3 py-2 rounded" value={customAmount} onChange={e => setCustomAmount(e.target.value)} required />
              <input type="text" placeholder="Reason (Required)" className="border px-3 py-2 rounded" value={customReason} onChange={e => setCustomReason(e.target.value)} required />
              <div className="flex justify-end gap-2 mt-4">
                <button type="button" onClick={() => setActiveModal(null)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded">Cancel</button>
                <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {activeModal === 'financialAid' && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex justify-center items-center">
          <div className="bg-white p-6 rounded shadow-lg w-full max-w-md">
            <h2 className="text-xl font-medium mb-4">Set Financial Aid</h2>
            <form onSubmit={handleSetAid} className="flex flex-col gap-4">
              <input type="number" placeholder="Student ID" className="border px-3 py-2 rounded" value={studentId} onChange={e => setStudentId(e.target.value)} required />
              <input type="number" placeholder="Reduction Amount" className="border px-3 py-2 rounded" value={aidAmount} onChange={e => setAidAmount(e.target.value)} required />
              <input type="text" placeholder="Reason for Aid" className="border px-3 py-2 rounded" value={aidReason} onChange={e => setAidReason(e.target.value)} required />
              <div className="flex justify-end gap-2 mt-4">
                <button type="button" onClick={() => setActiveModal(null)} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded">Cancel</button>
                <button type="submit" className="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700">Apply Aid</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminFeeManager;

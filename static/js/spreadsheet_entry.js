document.addEventListener('DOMContentLoaded', () => {
    const inputs = Array.from(document.querySelectorAll('.marks-input'));
    
    // Keyboard navigation
    inputs.forEach((input, index) => {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const nextInput = inputs[index + 1];
                if (nextInput) {
                    nextInput.focus();
                    nextInput.select();
                }
            } else if (e.key === 'ArrowRight' && input.selectionStart === input.value.length) {
                e.preventDefault();
                const nextInput = inputs[index + 1];
                if (nextInput) {
                    nextInput.focus();
                    nextInput.select();
                }
            } else if (e.key === 'ArrowLeft' && input.selectionStart === 0) {
                e.preventDefault();
                const prevInput = inputs[index - 1];
                if (prevInput) {
                    prevInput.focus();
                    prevInput.select();
                }
            }
        });
        
        // Focus select all text for easy overwriting
        input.addEventListener('focus', (e) => {
            e.target.select();
        });
        
        // Validation on blur
        input.addEventListener('blur', (e) => {
            let val = parseFloat(e.target.value);
            if (!isNaN(val)) {
                if (val < 0) {
                    alert('Marks cannot be negative');
                    e.target.value = '';
                    e.target.focus();
                }
                
                // Cross validation: Obt should not be greater than Full
                const container = e.target.closest('.input-group');
                if (container) {
                    const obtInput = container.querySelector('.obt-mark');
                    const fullInput = container.querySelector('.full-mark');
                    
                    if (obtInput.value !== '' && fullInput.value !== '') {
                        let obtVal = parseFloat(obtInput.value);
                        let fullVal = parseFloat(fullInput.value);
                        
                        if (!isNaN(obtVal) && !isNaN(fullVal) && obtVal > fullVal) {
                            alert(`Obtained mark (${obtVal}) cannot exceed Full mark (${fullVal})`);
                            e.target.value = '';
                        }
                    }
                }
            }
        });
    });

    // Save functionality
    const saveBtn = document.getElementById('save-marks-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            saveBtn.disabled = true;
            const originalContent = saveBtn.innerHTML;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

            const marksData = [];
            
            // Collect all inputs grouped by student and subject
            const subjectWrappers = document.querySelectorAll('.input-group');
            
            subjectWrappers.forEach(wrapper => {
                const obtInput = wrapper.querySelector('.obt-mark');
                const fullInput = wrapper.querySelector('.full-mark');
                
                if (obtInput && fullInput) {
                    const studentId = obtInput.dataset.studentId;
                    const subjectName = obtInput.dataset.subjectName;
                    const obtVal = obtInput.value;
                    const fullVal = fullInput.value;
                    
                    if (obtVal !== '' || fullVal !== '') {
                        marksData.push({
                            student_id: studentId,
                            subject_name: subjectName,
                            obtained_marks: obtVal,
                            full_marks: fullVal
                        });
                    }
                }
            });

            fetch(window.marksExamContext.saveUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    class_name: window.marksExamContext.className,
                    term_name: window.marksExamContext.termName,
                    marks: marksData
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert('Marks saved successfully!');
                } else {
                    alert('Error saving marks: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred while saving.');
            })
            .finally(() => {
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalContent;
            });
        });
    }
});

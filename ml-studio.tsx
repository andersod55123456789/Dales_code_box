import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, Play, Download, Info, ChevronRight, BarChart3, Target, Settings, Eye, Brain, FileText, Package } from 'lucide-react';
import * as Papa from 'papaparse';
import * as XLSX from 'xlsx';

// Sample datasets
const SAMPLE_DATASETS = {
  titanic: {
    name: "Titanic Survival",
    description: "Predict passenger survival",
    data: [
      { PassengerId: 1, Pclass: 3, Name: "John Doe", Sex: "male", Age: 22, SibSp: 1, Parch: 0, Fare: 7.25, Survived: 0 },
      { PassengerId: 2, Pclass: 1, Name: "Jane Smith", Sex: "female", Age: 38, SibSp: 1, Parch: 0, Fare: 71.28, Survived: 1 },
      { PassengerId: 3, Pclass: 3, Name: "Bob Johnson", Sex: "female", Age: 26, SibSp: 0, Parch: 0, Fare: 7.92, Survived: 1 },
      { PassengerId: 4, Pclass: 1, Name: "Alice Brown", Sex: "female", Age: 35, SibSp: 1, Parch: 0, Fare: 53.1, Survived: 1 },
      { PassengerId: 5, Pclass: 3, Name: "Charlie Wilson", Sex: "male", Age: 35, SibSp: 0, Parch: 0, Fare: 8.05, Survived: 0 }
    ]
  },
  housing: {
    name: "House Prices",
    description: "Predict house prices",
    data: [
      { Id: 1, LotArea: 8450, YearBuilt: 2003, BedroomAbvGr: 3, FullBath: 2, GarageArea: 548, SalePrice: 208500 },
      { Id: 2, LotArea: 9600, YearBuilt: 1976, BedroomAbvGr: 3, FullBath: 2, GarageArea: 460, SalePrice: 181500 },
      { Id: 3, LotArea: 11250, YearBuilt: 2001, BedroomAbvGr: 3, FullBath: 2, GarageArea: 608, SalePrice: 223500 },
      { Id: 4, LotArea: 9550, YearBuilt: 1915, BedroomAbvGr: 3, FullBath: 1, GarageArea: 642, SalePrice: 140000 },
      { Id: 5, LotArea: 14260, YearBuilt: 2000, BedroomAbvGr: 4, FullBath: 2, GarageArea: 836, SalePrice: 250000 }
    ]
  }
};

const MLStudio = () => {
  const [step, setStep] = useState(0);
  const [data, setData] = useState([]);
  const [columns, setColumns] = useState([]);
  const [columnTypes, setColumnTypes] = useState({});
  const [targetColumn, setTargetColumn] = useState('');
  const [taskType, setTaskType] = useState('');
  const [splitRatio, setSplitRatio] = useState({ train: 70, val: 15, test: 15 });
  const [selectedModel, setSelectedModel] = useState('automl');
  const [trainProgress, setTrainProgress] = useState(0);
  const [isTraining, setIsTraining] = useState(false);
  const [results, setResults] = useState(null);
  const [dataIssues, setDataIssues] = useState([]);
  const fileInputRef = useRef(null);

  const steps = [
    "Welcome",
    "Import Data", 
    "Select Target",
    "Data Checks",
    "Train/Test Split",
    "Model Selection",
    "Training",
    "Results",
    "Export"
  ];

  // Detect column types
  const detectColumnType = (values) => {
    const nonNullValues = values.filter(v => v != null && v !== '');
    if (nonNullValues.length === 0) return 'text';
    
    const numericCount = nonNullValues.filter(v => !isNaN(parseFloat(v)) && isFinite(v)).length;
    const dateCount = nonNullValues.filter(v => !isNaN(Date.parse(v))).length;
    
    if (numericCount / nonNullValues.length > 0.8) return 'numeric';
    if (dateCount / nonNullValues.length > 0.8) return 'datetime';
    
    const uniqueValues = new Set(nonNullValues).size;
    if (uniqueValues < nonNullValues.length * 0.1 && uniqueValues < 20) return 'categorical';
    
    return 'text';
  };

  // Process uploaded data
  const processData = (rawData) => {
    if (!rawData || rawData.length === 0) return;
    
    const cols = Object.keys(rawData[0]);
    setColumns(cols);
    
    const types = {};
    cols.forEach(col => {
      const values = rawData.map(row => row[col]);
      types[col] = detectColumnType(values);
    });
    setColumnTypes(types);
    setData(rawData);
    
    // Check for data issues
    const issues = checkDataIssues(rawData, cols);
    setDataIssues(issues);
  };

  // Check for common data issues
  const checkDataIssues = (data, cols) => {
    const issues = [];
    
    cols.forEach(col => {
      const values = data.map(row => row[col]);
      const missingCount = values.filter(v => v == null || v === '').length;
      const missingPct = (missingCount / values.length) * 100;
      
      if (missingPct > 10) {
        issues.push({
          type: 'missing',
          column: col,
          severity: missingPct > 50 ? 'high' : 'medium',
          message: `${col} has ${missingPct.toFixed(1)}% missing values`
        });
      }
      
      if (columnTypes[col] === 'categorical') {
        const uniqueValues = new Set(values.filter(v => v != null && v !== '')).size;
        if (uniqueValues > values.length * 0.5) {
          issues.push({
            type: 'cardinality',
            column: col,
            severity: 'medium',
            message: `${col} has very high cardinality (${uniqueValues} unique values)`
          });
        }
      }
    });
    
    return issues;
  };

  // Handle file upload
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    const fileExtension = file.name.split('.').pop().toLowerCase();
    
    if (fileExtension === 'csv' || fileExtension === 'tsv') {
      const delimiter = fileExtension === 'tsv' ? '\t' : ',';
      Papa.parse(file, {
        header: true,
        delimiter: delimiter,
        skipEmptyLines: true,
        dynamicTyping: true,
        complete: (results) => {
          processData(results.data);
          setStep(2);
        }
      });
    } else if (fileExtension === 'xlsx' || fileExtension === 'xls') {
      const reader = new FileReader();
      reader.onload = (e) => {
        const data = e.target.result;
        const workbook = XLSX.read(data, { type: 'array' });
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];
        const jsonData = XLSX.utils.sheet_to_json(worksheet);
        processData(jsonData);
        setStep(2);
      };
      reader.readAsArrayBuffer(file);
    }
  };

  // Load sample dataset
  const loadSampleDataset = (key) => {
    const sample = SAMPLE_DATASETS[key];
    processData(sample.data);
    setStep(2);
  };

  // Detect task type based on target column
  const detectTaskType = (targetCol) => {
    if (!targetCol || !data.length) return '';
    
    const values = data.map(row => row[targetCol]).filter(v => v != null && v !== '');
    const uniqueValues = new Set(values).size;
    
    if (columnTypes[targetCol] === 'numeric' && uniqueValues > 10) {
      return 'regression';
    } else if (uniqueValues === 2) {
      return 'binary classification';
    } else if (uniqueValues <= 10) {
      return 'multi-class classification';
    } else {
      return 'regression';
    }
  };

  // Simulate model training
  const simulateTraining = () => {
    setIsTraining(true);
    setTrainProgress(0);
    
    const interval = setInterval(() => {
      setTrainProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsTraining(false);
          
          // Generate mock results
          const mockResults = {
            bestModel: selectedModel === 'automl' ? 'Random Forest' : selectedModel,
            metrics: taskType.includes('classification') ? {
              accuracy: 0.85 + Math.random() * 0.1,
              rocAuc: 0.80 + Math.random() * 0.15,
              f1Score: 0.82 + Math.random() * 0.12
            } : {
              mae: 50000 + Math.random() * 20000,
              rmse: 75000 + Math.random() * 25000,
              r2: 0.7 + Math.random() * 0.2
            },
            featureImportance: columns
              .filter(col => col !== targetColumn)
              .slice(0, 5)
              .map(col => ({
                feature: col,
                importance: Math.random()
              }))
              .sort((a, b) => b.importance - a.importance)
          };
          
          setResults(mockResults);
          setStep(7);
          return 100;
        }
        return prev + Math.random() * 15 + 5;
      });
    }, 200);
  };

  // Format metric display
  const formatMetric = (key, value) => {
    if (key.includes('accuracy') || key.includes('Score') || key === 'r2') {
      return (value * 100).toFixed(1) + '%';
    }
    return value.toLocaleString();
  };

  const renderStep = () => {
    switch(step) {
      case 0: // Welcome
        return (
          <div className="text-center max-w-2xl mx-auto">
            <div className="mb-8">
              <Brain className="w-16 h-16 text-blue-500 mx-auto mb-4" />
              <h1 className="text-3xl font-bold text-gray-800 mb-4">Welcome to ML Studio</h1>
              <p className="text-lg text-gray-600">
                Train machine learning models without coding. Load your data and we'll guide you through every step.
              </p>
            </div>
            
            <div className="space-y-4">
              <button
                onClick={() => setStep(1)}
                className="w-full bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors flex items-center justify-center gap-2"
              >
                <Upload className="w-5 h-5" />
                Load Your Data
              </button>
              
              <div className="text-gray-500">or try a sample dataset:</div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Object.entries(SAMPLE_DATASETS).map(([key, dataset]) => (
                  <button
                    key={key}
                    onClick={() => loadSampleDataset(key)}
                    className="p-4 border-2 border-gray-200 rounded-lg hover:border-blue-300 transition-colors text-left"
                  >
                    <h3 className="font-medium text-gray-800">{dataset.name}</h3>
                    <p className="text-sm text-gray-600">{dataset.description}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        );

      case 1: // Import Data
        return (
          <div className="max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Import Your Data</h2>
            
            <div 
              className="border-2 border-dashed border-gray-300 rounded-lg p-12 text-center hover:border-blue-400 transition-colors cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <p className="text-lg text-gray-600 mb-2">Drop your file here or click to browse</p>
              <p className="text-sm text-gray-500">Supports: Excel (.xlsx, .xls), CSV, TSV</p>
              <p className="text-sm text-gray-500">Up to 1M rows, 200 columns</p>
            </div>
            
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls,.tsv"
              onChange={handleFileUpload}
              className="hidden"
            />
          </div>
        );

      case 2: // Select Target
        return (
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Select Target Column</h2>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <div className="flex items-center gap-2 mb-2">
                <Info className="w-5 h-5 text-blue-600" />
                <span className="font-medium text-blue-800">What are we trying to predict?</span>
              </div>
              <p className="text-blue-700">Choose the column that contains the values you want to predict.</p>
            </div>
            
            {data.length > 0 && (
              <div className="bg-white border rounded-lg overflow-hidden mb-6">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        {columns.slice(0, 6).map(col => (
                          <th key={col} className="px-4 py-3 text-left text-sm font-medium text-gray-700">
                            {col}
                            <div className="text-xs text-gray-500 font-normal">
                              {columnTypes[col]}
                            </div>
                          </th>
                        ))}
                        {columns.length > 6 && (
                          <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">
                            +{columns.length - 6} more...
                          </th>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {data.slice(0, 3).map((row, i) => (
                        <tr key={i} className="border-t">
                          {columns.slice(0, 6).map(col => (
                            <td key={col} className="px-4 py-2 text-sm text-gray-600">
                              {String(row[col] || '').substring(0, 20)}
                              {String(row[col] || '').length > 20 ? '...' : ''}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            
            <div className="space-y-4">
              <label className="block text-sm font-medium text-gray-700">
                Target Column
              </label>
              <select
                value={targetColumn}
                onChange={(e) => {
                  setTargetColumn(e.target.value);
                  setTaskType(detectTaskType(e.target.value));
                }}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Choose a column...</option>
                {columns.map(col => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
              
              {taskType && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <div className="flex items-center gap-2">
                    <Target className="w-5 h-5 text-green-600" />
                    <span className="font-medium text-green-800">
                      Detected task: {taskType}
                    </span>
                  </div>
                  <p className="text-green-700 text-sm mt-1">
                    {taskType.includes('classification') 
                      ? 'We\'ll predict categories or classes'
                      : 'We\'ll predict numerical values'
                    }
                  </p>
                </div>
              )}
              
              <button
                onClick={() => setStep(3)}
                disabled={!targetColumn}
                className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                Continue
              </button>
            </div>
          </div>
        );

      case 3: // Data Checks
        return (
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Data Quality Check</h2>
            
            <div className="space-y-4 mb-6">
              {dataIssues.length === 0 ? (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center">
                      <div className="w-2 h-2 bg-white rounded-full"></div>
                    </div>
                    <span className="font-medium text-green-800">Data looks good!</span>
                  </div>
                  <p className="text-green-700 text-sm mt-1">
                    No major issues detected. Ready to proceed with training.
                  </p>
                </div>
              ) : (
                dataIssues.map((issue, i) => (
                  <div key={i} className={`border rounded-lg p-4 ${
                    issue.severity === 'high' ? 'bg-red-50 border-red-200' :
                    issue.severity === 'medium' ? 'bg-yellow-50 border-yellow-200' :
                    'bg-blue-50 border-blue-200'
                  }`}>
                    <div className="flex items-center justify-between">
                      <span className={`font-medium ${
                        issue.severity === 'high' ? 'text-red-800' :
                        issue.severity === 'medium' ? 'text-yellow-800' :
                        'text-blue-800'
                      }`}>
                        {issue.message}
                      </span>
                      <button className="text-sm bg-white px-3 py-1 rounded border hover:bg-gray-50">
                        Auto-fix
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="bg-white border rounded-lg p-4">
                <div className="text-2xl font-bold text-blue-600">{data.length}</div>
                <div className="text-sm text-gray-600">Total Rows</div>
              </div>
              <div className="bg-white border rounded-lg p-4">
                <div className="text-2xl font-bold text-green-600">{columns.length}</div>
                <div className="text-sm text-gray-600">Features</div>
              </div>
              <div className="bg-white border rounded-lg p-4">
                <div className="text-2xl font-bold text-purple-600">
                  {new Set(data.map(row => row[targetColumn])).size}
                </div>
                <div className="text-sm text-gray-600">Unique Targets</div>
              </div>
            </div>
            
            <button
              onClick={() => setStep(4)}
              className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
            >
              Continue to Split Data
            </button>
          </div>
        );

      case 4: // Train/Test Split
        return (
          <div className="max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Split Your Data</h2>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <div className="flex items-center gap-2 mb-2">
                <Info className="w-5 h-5 text-blue-600" />
                <span className="font-medium text-blue-800">Why split the data?</span>
              </div>
              <p className="text-blue-700">
                We'll use most data to train the model, some to tune it, and the rest to test how well it works on new data.
              </p>
            </div>
            
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Data Split Ratios
                </label>
                <div className="space-y-4">
                  <div className="flex items-center gap-4">
                    <div className="w-20 text-sm text-gray-600">Training:</div>
                    <input
                      type="range"
                      min="50"
                      max="80"
                      value={splitRatio.train}
                      onChange={(e) => {
                        const train = parseInt(e.target.value);
                        const remaining = 100 - train;
                        setSplitRatio({
                          train,
                          val: Math.floor(remaining / 2),
                          test: remaining - Math.floor(remaining / 2)
                        });
                      }}
                      className="flex-1"
                    />
                    <div className="w-12 text-sm font-medium">{splitRatio.train}%</div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="w-20 text-sm text-gray-600">Validation:</div>
                    <div className="flex-1 bg-gray-200 h-2 rounded"></div>
                    <div className="w-12 text-sm font-medium">{splitRatio.val}%</div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="w-20 text-sm text-gray-600">Test:</div>
                    <div className="flex-1 bg-gray-200 h-2 rounded"></div>
                    <div className="w-12 text-sm font-medium">{splitRatio.test}%</div>
                  </div>
                </div>
              </div>
              
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <div className="font-medium text-blue-600">
                      {Math.floor(data.length * splitRatio.train / 100)} rows
                    </div>
                    <div className="text-sm text-gray-600">Train Model</div>
                  </div>
                  <div>
                    <div className="font-medium text-green-600">
                      {Math.floor(data.length * splitRatio.val / 100)} rows
                    </div>
                    <div className="text-sm text-gray-600">Tune Model</div>
                  </div>
                  <div>
                    <div className="font-medium text-purple-600">
                      {Math.floor(data.length * splitRatio.test / 100)} rows
                    </div>
                    <div className="text-sm text-gray-600">Test Model</div>
                  </div>
                </div>
              </div>
              
              <button
                onClick={() => setStep(5)}
                className="w-full bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
              >
                Continue to Model Selection
              </button>
            </div>
          </div>
        );

      case 5: // Model Selection
        return (
          <div className="max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Choose Your Model</h2>
            
            <div className="space-y-4 mb-6">
              <div 
                className={`border-2 rounded-lg p-4 cursor-pointer transition-colors ${
                  selectedModel === 'automl' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => setSelectedModel('automl')}
              >
                <div className="flex items-center gap-3">
                  <input type="radio" checked={selectedModel === 'automl'} onChange={() => {}} className="text-blue-500" />
                  <div>
                    <h3 className="font-medium">AutoML (Recommended)</h3>
                    <p className="text-sm text-gray-600">
                      Tries multiple models and picks the best one. Great for beginners.
                    </p>
                  </div>
                </div>
              </div>
              
              <div 
                className={`border-2 rounded-lg p-4 cursor-pointer transition-colors ${
                  selectedModel === 'random_forest' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => setSelectedModel('random_forest')}
              >
                <div className="flex items-center gap-3">
                  <input type="radio" checked={selectedModel === 'random_forest'} onChange={() => {}} className="text-blue-500" />
                  <div>
                    <h3 className="font-medium">Random Forest</h3>
                    <p className="text-sm text-gray-600">
                      Reliable and interpretable. Works well with mixed data types.
                    </p>
                  </div>
                </div>
              </div>
              
              <div 
                className={`border-2 rounded-lg p-4 cursor-pointer transition-colors ${
                  selectedModel === 'gradient_boost' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => setSelectedModel('gradient_boost')}
              >
                <div className="flex items-center gap-3">
                  <input type="radio" checked={selectedModel === 'gradient_boost'} onChange={() => {}} className="text-blue-500" />
                  <div>
                    <h3 className="font-medium">Gradient Boosting</h3>
                    <p className="text-sm text-gray-600">
                      Often achieves high accuracy. May take longer to train.
                    </p>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
              <div className="flex items-center gap-2 mb-2">
                <Settings className="w-5 h-5 text-yellow-600" />
                <span className="font-medium text-yellow-800">Training Settings</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-sm text-yellow-700">Speed</span>
                <input type="range" className="flex-1" defaultValue="50" />
                <span className="text-sm text-yellow-700">Accuracy</span>
              </div>
            </div>
            
            <button
              onClick={() => setStep(6)}
              className="w-full bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors flex items-center justify-center gap-2"
            >
              <Play className="w-5 h-5" />
              Start Training
            </button>
          </div>
        );

      case 6: // Training
        return (
          <div className="max-w-2xl mx-auto text-center">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Training Your Model</h2>
            
            <div className="mb-8">
              <div className="w-32 h-32 mx-auto mb-6 relative">
                <svg className="w-32 h-32 transform -rotate-90" viewBox="0 0 120 120">
                  <circle
                    cx="60"
                    cy="60"
                    r="50"
                    fill="none"
                    stroke="#e5e7eb"
                    strokeWidth="10"
                  />
                  <circle
                    cx="60"
                    cy="60"
                    r="50"
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="10"
                    strokeLinecap="round"
                    strokeDasharray={`${2 * Math.PI * 50}`}
                    strokeDashoffset={`${2 * Math.PI * 50 * (1 - trainProgress / 100)}`}
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-2xl font-bold text-blue-600">{Math.round(trainProgress)}%</span>
                </div>
              </div>
              
              <div className="space-y-2 text-sm text-gray-600">
                <div>Training model with {selectedModel === 'automl' ? 'AutoML' : selectedModel.replace('_', ' ')}...</div>
                <div>Processing {data.length} rows with {columns.length - 1} features</div>
                <div>This usually takes 2-5 minutes</div>
              </div>
            </div>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <div className="text-sm text-blue-700">
                💡 <strong>Training Tip:</strong> The model is learning patterns in your data to make predictions on new examples.
              </div>
            </div>
            
            {!isTraining && trainProgress === 0 && (
              <button
                onClick={simulateTraining}
                className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
              >
                Start Training
              </button>
            )}
            
            {isTraining && (
              <button
                className="bg-red-500 text-white px-6 py-3 rounded-lg hover:bg-red-600 transition-colors"
                onClick={() => setIsTraining(false)}
              >
                Cancel Training
              </button>
            )}
          </div>
        );

      case 7: // Results
        return (
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Training Results</h2>
            
            {results && (
              <div className="space-y-6">
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center">
                      <div className="w-2 h-2 bg-white rounded-full"></div>
                    </div>
                    <span className="font-medium text-green-800">Training Complete!</span>
                  </div>
                  <p className="text-green-700">
                    Best model: <strong>{results.bestModel}</strong>
                  </p>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {Object.entries(results.metrics).map(([key, value]) => (
                    <div key={key} className="bg-white border rounded-lg p-4">
                      <div className="text-2xl font-bold text-blue-600">
                        {formatMetric(key, value)}
                      </div>
                      <div className="text-sm text-gray-600 capitalize">
                        {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
                      </div>
                    </div>
                  ))}
                </div>
                
                <div className="bg-white border rounded-lg p-6">
                  <h3 className="text-lg font-medium text-gray-800 mb-4">Most Important Features</h3>
                  <div className="space-y-3">
                    {results.featureImportance.map((feature, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <div className="w-24 text-sm text-gray-600">{feature.feature}</div>
                        <div className="flex-1 bg-gray-200 rounded-full h-3">
                          <div 
                            className="bg-blue-500 rounded-full h-3"
                            style={{ width: `${feature.importance * 100}%` }}
                          ></div>
                        </div>
                        <div className="w-12 text-sm text-gray-500">
                          {(feature.importance * 100).toFixed(0)}%
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="bg-white border rounded-lg p-6">
                  <h3 className="text-lg font-medium text-gray-800 mb-4">Model Explanation</h3>
                  <div className="text-gray-600">
                    {taskType.includes('classification') ? (
                      <p>
                        Your model achieved {formatMetric('accuracy', results.metrics.accuracy)} accuracy, 
                        meaning it correctly predicted the target in {formatMetric('accuracy', results.metrics.accuracy)} of test cases.
                        The most important features for making predictions are shown above.
                      </p>
                    ) : (
                      <p>
                        Your model has an R² score of {formatMetric('r2', results.metrics.r2)}, 
                        meaning it explains {formatMetric('r2', results.metrics.r2)} of the variation in your target variable.
                        The average error is {formatMetric('mae', results.metrics.mae)}.
                      </p>
                    )}
                  </div>
                </div>
                
                <button
                  onClick={() => setStep(8)}
                  className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
                >
                  Export Results
                </button>
              </div>
            )}
          </div>
        );

      case 8: // Export
        return (
          <div className="max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Export Your Work</h2>
            
            <div className="space-y-4">
              <div className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer">
                <div className="flex items-center gap-3">
                  <FileText className="w-8 h-8 text-blue-500" />
                  <div>
                    <h3 className="font-medium">Jupyter Notebook</h3>
                    <p className="text-sm text-gray-600">Complete code with all steps and visualizations</p>
                  </div>
                  <Download className="w-5 h-5 text-gray-400 ml-auto" />
                </div>
              </div>
              
              <div className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer">
                <div className="flex items-center gap-3">
                  <Package className="w-8 h-8 text-green-500" />
                  <div>
                    <h3 className="font-medium">Python Package</h3>
                    <p className="text-sm text-gray-600">Ready-to-use prediction script with requirements.txt</p>
                  </div>
                  <Download className="w-5 h-5 text-gray-400 ml-auto" />
                </div>
              </div>
              
              <div className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer">
                <div className="flex items-center gap-3">
                  <BarChart3 className="w-8 h-8 text-purple-500" />
                  <div>
                    <h3 className="font-medium">Predictions CSV</h3>
                    <p className="text-sm text-gray-600">Model predictions on your test data</p>
                  </div>
                  <Download className="w-5 h-5 text-gray-400 ml-auto" />
                </div>
              </div>
              
              <div className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer">
                <div className="flex items-center gap-3">
                  <Eye className="w-8 h-8 text-orange-500" />
                  <div>
                    <h3 className="font-medium">Model Report</h3>
                    <p className="text-sm text-gray-600">Detailed analysis and insights in PDF format</p>
                  </div>
                  <Download className="w-5 h-5 text-gray-400 ml-auto" />
                </div>
              </div>
            </div>
            
            <div className="mt-8 pt-6 border-t">
              <button
                onClick={() => {
                  setStep(0);
                  setData([]);
                  setColumns([]);
                  setTargetColumn('');
                  setResults(null);
                }}
                className="w-full bg-gray-500 text-white px-6 py-3 rounded-lg hover:bg-gray-600 transition-colors"
              >
                Start New Project
              </button>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <Brain className="w-8 h-8 text-blue-500" />
              <span className="text-xl font-bold text-gray-800">ML Studio</span>
            </div>
            <div className="text-sm text-gray-500">
              {step > 0 && `Step ${step} of ${steps.length - 1}: ${steps[step]}`}
            </div>
          </div>
        </div>
      </header>

      {/* Progress Bar */}
      {step > 0 && (
        <div className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center py-4">
              {steps.slice(1).map((stepName, i) => (
                <React.Fragment key={i}>
                  <div className={`flex items-center gap-2 ${
                    i + 1 <= step ? 'text-blue-600' : 'text-gray-400'
                  }`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                      i + 1 <= step ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'
                    }`}>
                      {i + 1}
                    </div>
                    <span className="text-sm font-medium">{stepName}</span>
                  </div>
                  {i < steps.length - 2 && (
                    <ChevronRight className="w-4 h-4 mx-2 text-gray-400" />
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {renderStep()}
      </main>
    </div>
  );
};

export default MLStudio;
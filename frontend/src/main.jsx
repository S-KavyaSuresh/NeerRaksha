import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { MotionConfig } from 'framer-motion'
import DashboardLayout from './layouts/DashboardLayout'
import './styles/tokens.css'
import './styles/dashboard.css'
import './styles/workflows.css'
import 'cesium/Build/Cesium/Widgets/widgets.css'

ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><MotionConfig reducedMotion="user"><BrowserRouter><Routes><Route path="/" element={<Navigate to="/overview" replace/>}/>{['overview','scenario','simulation','comparison','impact','exports'].map(path=><Route key={path} path={`/${path}`} element={<DashboardLayout/>}/>)}<Route path="*" element={<Navigate to="/overview" replace/>}/></Routes></BrowserRouter></MotionConfig></React.StrictMode>)

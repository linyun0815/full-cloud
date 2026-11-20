package cn.full.cloud.module.hrm.dal.mysql.salary.config;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.hrm.dal.dataobject.salary.config.HrmSalaryConfigDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface HrmSalaryConfigMapper extends BaseMapperX<HrmSalaryConfigDO> {

    default HrmSalaryConfigDO selectFirst() {
        return selectFirstOne(new LambdaQueryWrapperX<HrmSalaryConfigDO>()
                .orderByAsc(HrmSalaryConfigDO::getId));
    }

}

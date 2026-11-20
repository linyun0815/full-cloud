package cn.full.cloud.module.hrm.dal.mysql.insurance.config;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.hrm.dal.dataobject.insurance.config.HrmInsuranceSchemeDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface HrmInsuranceSchemeMapper extends BaseMapperX<HrmInsuranceSchemeDO> {

    default HrmInsuranceSchemeDO selectByName(String name) {
        return selectLastOne(new LambdaQueryWrapperX<HrmInsuranceSchemeDO>()
                .eq(HrmInsuranceSchemeDO::getName, name)
                .orderByAsc(HrmInsuranceSchemeDO::getId));
    }

    default HrmInsuranceSchemeDO selectByIdForUpdate(Long id) {
        return selectOneForUpdate(HrmInsuranceSchemeDO::getId, id);
    }

    default List<HrmInsuranceSchemeDO> selectListByIdDesc() {
        return selectList(new LambdaQueryWrapperX<HrmInsuranceSchemeDO>().orderByDesc(HrmInsuranceSchemeDO::getId));
    }

    default List<HrmInsuranceSchemeDO> selectListByAreaId(Integer areaId) {
        return selectList(new LambdaQueryWrapperX<HrmInsuranceSchemeDO>()
                .eq(HrmInsuranceSchemeDO::getAreaId, areaId)
                .orderByDesc(HrmInsuranceSchemeDO::getId));
    }

}
